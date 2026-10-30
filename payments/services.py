"""All payment state changes go through these functions.

Each one runs in a database transaction and locks the rows it changes, so two
admins clicking "Approve" at once (or a webhook racing a capture) cannot pay
an order twice.
"""

import logging
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.utils import timezone

from core.notifications import (
    notify_capstone_status,
    notify_payment_approved,
    notify_payment_rejected,
    notify_payment_submitted,
)
from payments.models import Payment
from payments.payables import lock_payable, payment_filter

logger = logging.getLogger("payments")


class PaymentError(Exception):
    """A payment action was refused; the message is safe to show to the user."""


GATEWAY_PROVIDERS = ("paypal_checkout", "card_paypal")


def _lock_payment(payment_id):
    # Always lock the parent before its payment, including refunds and webhooks.
    original = Payment.objects.get(pk=payment_id)
    payable = lock_payable(original.payable)
    payment = Payment.objects.select_for_update().get(pk=payment_id)
    if payment.order_id:
        payment.order = payable
    else:
        payment.capstone_request = payable
    return payment, payable


def _validate_payment_target(payment, payable):
    # Existing payment attempts must still settle, including after product sales retire.
    existing_order_payment = payable.payable_kind == "order" and payable.status in {
        "pending", "rejected", "awaiting_verification",
    }
    if not payable.can_be_paid and not existing_order_payment:
        raise PaymentError("This order or request can no longer receive payment. Please contact us if you were charged.")
    if payment.amount != payable.amount_due or payment.currency != payable.currency:
        raise PaymentError("The quote or amount has changed. Please contact us before paying again.")
    if payable.payment_block_reason:
        raise PaymentError(payable.payment_block_reason)
    if Payment.objects.filter(**payment_filter(payable), status=Payment.Status.COMPLETED).exclude(pk=payment.pk).exists():
        raise PaymentError("This item has already been paid. Please contact us about the extra payment.")


def _after_paid(payment):
    notify_payment_approved(payment)
    if payment.capstone_request_id:
        notify_capstone_status(payment.capstone_request)


@transaction.atomic
def submit_manual_payment(payable, user, provider, provider_reference, proof_image=None):
    payable = lock_payable(payable)
    if payable.customer.pk != user.pk:
        raise PaymentError("You can only submit payment for your own order or request.")
    if not payable.can_be_paid:
        raise PaymentError("This item cannot be paid right now. Refresh the page to see its current status.")
    if payable.payment_block_reason:
        raise PaymentError(payable.payment_block_reason)
    if Payment.objects.filter(**payment_filter(payable), status=Payment.Status.AWAITING_VERIFICATION).exists():
        raise PaymentError("A payment for this item is already waiting for verification.")
    try:
        with transaction.atomic():
            payment = Payment.objects.create(
                **payment_filter(payable),
                customer=user,
                amount=payable.amount_due,
                currency=payable.currency,
                method=provider.method,
                provider=provider.code,
                status=Payment.Status.AWAITING_VERIFICATION,
                provider_reference=provider_reference.strip().upper(),
                proof_image=proof_image or "",
            )
    except IntegrityError as exc:
        raise PaymentError("This reference number has already been submitted. Please check it and try again.") from exc
    payable.on_payment_submitted(payment)
    transaction.on_commit(lambda: notify_payment_submitted(payment))
    logger.info("Manual payment %s submitted for %s", payment.pk, payable.reference)
    return payment


def approve_payment(payment_id, staff_user, notes=""):
    """Approve a manual payment. Returns (payment, changed). Approving twice is a no-op."""
    with transaction.atomic():
        payment, payable = _lock_payment(payment_id)
        if payment.status == Payment.Status.COMPLETED:
            return payment, False
        if payment.status != Payment.Status.AWAITING_VERIFICATION:
            raise PaymentError(f"Only payments awaiting verification can be approved (this one is {payment.get_status_display()}).")
        if not payment.is_manual:
            raise PaymentError("Gateway payments must be confirmed by the payment provider.")
        _validate_payment_target(payment, payable)
        payment.status = Payment.Status.COMPLETED
        payment.verified_by = staff_user
        payment.verified_at = timezone.now()
        if notes:
            payment.admin_notes = notes
        payment.save()
        payable.mark_paid(payment)
        transaction.on_commit(lambda: _after_paid(payment))
    logger.info("Payment %s approved by %s", payment.pk, staff_user)
    return payment, True


def reject_payment(payment_id, staff_user, reason):
    reason = (reason or "").strip()
    if not reason:
        raise PaymentError("Please give a reason. The customer will see it.")
    with transaction.atomic():
        payment, payable = _lock_payment(payment_id)
        if payment.status != Payment.Status.AWAITING_VERIFICATION:
            raise PaymentError("Only payments awaiting verification can be rejected.")
        if not payment.is_manual:
            raise PaymentError("Gateway payments must be resolved by the payment provider.")
        payment.status = Payment.Status.REJECTED
        payment.rejection_reason = reason
        payment.verified_by = staff_user
        payment.verified_at = timezone.now()
        payment.save()
        payable.on_payment_rejected(payment)
        transaction.on_commit(lambda: notify_payment_rejected(payment))
    logger.info("Payment %s rejected by %s", payment.pk, staff_user)
    return payment


def refund_payable(payable, staff_user, notes=""):
    """Mark a paid order/request as refunded. The money itself is returned in PayPal/GCash."""
    with transaction.atomic():
        payable = lock_payable(payable)
        payment = (
            Payment.objects.select_for_update()
            .filter(**payment_filter(payable), status=Payment.Status.COMPLETED)
            .first()
        )
        if not payment:
            raise PaymentError("Only a confirmed payment can be marked as refunded.")
        payment.status = Payment.Status.REFUNDED
        actor = f"staff {staff_user.pk}" if staff_user else "PayPal webhook"
        payment.admin_notes = "\n".join(filter(None, [payment.admin_notes, f"Refund recorded by {actor}: {notes}".strip()]))
        payment.save()
        payable.on_payment_refunded(payment)
    logger.info("%s refunded by %s", payable.reference, staff_user)
    return payment


def start_automated_payment(payable, user, provider):
    """Reuse a pending gateway attempt so retries keep the same idempotency key."""
    with transaction.atomic():
        payable = lock_payable(payable)
        if payable.customer.pk != user.pk:
            raise PaymentError("You can only pay for your own order or request.")
        if not payable.can_be_paid:
            raise PaymentError("This item cannot be paid right now.")
        if payable.payment_block_reason:
            raise PaymentError(payable.payment_block_reason)
        if Payment.objects.filter(**payment_filter(payable), status=Payment.Status.AWAITING_VERIFICATION).exists():
            raise PaymentError("A payment for this item is already being verified.")
        existing = Payment.objects.filter(
            **payment_filter(payable), provider=provider.code, status=Payment.Status.PENDING,
            amount=payable.amount_due, currency=payable.currency,
        ).first()
        if existing:
            return existing
        return Payment.objects.create(
            **payment_filter(payable),
            customer=user,
            amount=payable.amount_due,
            currency=payable.currency,
            method=provider.method,
            provider=provider.code,
            status=Payment.Status.PENDING,
        )


def record_gateway_refund(payment_id, capture_id, raw):
    """Record a provider-confirmed full refund, even if its completion event arrived late."""
    with transaction.atomic():
        payment, payable = _lock_payment(payment_id)
        if payment.provider not in GATEWAY_PROVIDERS:
            raise PaymentError("This payment does not belong to the gateway.")
        if payment.capture_id and payment.capture_id != capture_id:
            raise PaymentError("The refunded capture does not match this payment.")
        if payment.status == Payment.Status.REFUNDED:
            return payment
        was_completed = payment.status == Payment.Status.COMPLETED
        payment.status = Payment.Status.REFUNDED
        payment.capture_id = capture_id
        payment.raw_response = raw
        payment.admin_notes = "\n".join(filter(None, [payment.admin_notes, "Full refund confirmed by PayPal webhook."]))
        payment.save()
        if was_completed:
            payable.on_payment_refunded(payment)
    return payment


def complete_automated_payment(payment_id, capture_id, amount, currency, raw):
    """Mark a gateway payment as completed after the server verified the capture.

    Returns (payment, changed). Safe to call from both the capture endpoint and the webhook.
    """
    error = None
    with transaction.atomic():
        payment, payable = _lock_payment(payment_id)
        if payment.provider not in GATEWAY_PROVIDERS:
            raise PaymentError("This payment does not belong to the gateway.")
        if payment.status == Payment.Status.COMPLETED:
            if payment.capture_id != capture_id:
                raise PaymentError("This payment already has a different capture. Please contact us.")
            return payment, False
        if payment.status not in (Payment.Status.PENDING, Payment.Status.AWAITING_VERIFICATION):
            raise PaymentError(f"Payment {payment.pk} is {payment.status}; refusing to complete it.")
        try:
            received = Decimal(str(amount))
            valid_amount = received.is_finite() and received == payment.amount and currency == payment.currency
        except (InvalidOperation, ValueError, TypeError):
            valid_amount = False
        if not isinstance(capture_id, str) or not capture_id or len(capture_id) > 100:
            raise PaymentError("The gateway did not supply a valid capture ID.")
        if Payment.objects.filter(capture_id=capture_id).exclude(pk=payment.pk).exists():
            raise PaymentError("This capture is already assigned to another payment.")
        try:
            _validate_payment_target(payment, payable)
        except PaymentError as exc:
            error = str(exc)
        if not valid_amount:
            error = "The paid amount does not match. Please contact us with your PayPal receipt."
        if error:
            # Commit the failure and receipt before returning an error to the caller.
            payment.status = Payment.Status.FAILED
            payment.capture_id = capture_id
            payment.admin_notes = f"{error} Received {amount} {currency}; expected {payment.amount} {payment.currency}."
            payment.raw_response = raw
            payment.save()
        else:
            payment.status = Payment.Status.COMPLETED
            payment.capture_id = capture_id
            payment.raw_response = raw
            payment.verified_at = timezone.now()
            payment.save()
            payable.mark_paid(payment)
            transaction.on_commit(lambda: _after_paid(payment))
    if error:
        logger.error("Payment %s could not be applied: %s", payment.pk, error)
        raise PaymentError(error)
    logger.info("Automated payment %s completed (capture %s)", payment.pk, capture_id)
    return payment, True


def mark_payment_failed(payment, raw, note):
    with transaction.atomic():
        payment, _payable = _lock_payment(payment.pk)
        if payment.status in (Payment.Status.PENDING, Payment.Status.AWAITING_VERIFICATION):
            payment.status = Payment.Status.FAILED
            payment.raw_response = raw
            payment.admin_notes = note
            payment.save()
    return payment
