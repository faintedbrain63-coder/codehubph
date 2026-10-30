import json
import logging
import re
from decimal import Decimal, InvalidOperation

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404, HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST

from payments.forms import ManualPaymentForm
from payments.models import Payment, WebhookEvent
from payments.payables import get_user_payable_or_404, payment_filter
from payments.providers import get_checkout_providers, get_provider_for_method, paypal_api
from payments.services import (
    PaymentError,
    GATEWAY_PROVIDERS,
    _lock_payment,
    _validate_payment_target,
    complete_automated_payment,
    mark_payment_failed,
    record_gateway_refund,
    start_automated_payment,
    submit_manual_payment,
)

logger = logging.getLogger("payments")


def _render_checkout(request, payable, kind, selected=None, bound_form=None, status=200):
    """Render the checkout page. `bound_form` replaces one manual form to show its errors."""
    providers = get_checkout_providers()
    panels = []
    for provider in providers:
        configured = provider.is_configured()
        panel = {"provider": provider, "configured": configured}
        if configured:
            panel.update(provider.get_panel_context(request, payable))
            if provider.is_manual:
                if bound_form is not None and bound_form.provider.code == provider.code:
                    panel["form"] = bound_form
                else:
                    panel["form"] = ManualPaymentForm(provider=provider)
        panels.append(panel)

    available = {p["provider"].method for p in panels if p["configured"]}
    if selected not in available:
        selected = next((p["provider"].method for p in panels if p["configured"]), "")

    sdk_panels = [p for p in panels if p["configured"] and getattr(p["provider"], "uses_paypal_sdk", False)]
    sdk_url = ""
    if sdk_panels:
        components = ["buttons"]
        if any(p["provider"].code == "card_paypal" for p in sdk_panels):
            components.append("card-fields")
        sdk_url = (
            f"https://www.paypal.com/sdk/js?client-id={settings.PAYPAL_CLIENT_ID}"
            f"&currency={payable.currency}&intent=capture&components={','.join(components)}"
        )

    context = {
        "payable": payable,
        "kind": kind,
        "panels": panels,
        "selected": selected,
        "has_payment_methods": bool(available),
        "last_rejected": Payment.objects.filter(
            **payment_filter(payable), status=Payment.Status.REJECTED
        ).first(),
        "paypal_sdk_url": sdk_url,
        "checkout_config": {
            "kind": kind,
            "reference": payable.reference,
            "sdkEnabled": bool(sdk_url),
            "createUrl": reverse("payments:paypal_create"),
            "captureUrl": reverse("payments:paypal_capture"),
        },
    }
    return render(request, "payments/checkout.html", context, status=status)


@login_required
def checkout(request, kind, reference):
    payable = get_user_payable_or_404(request.user, kind, reference)
    awaiting = Payment.objects.filter(
        **payment_filter(payable), status=Payment.Status.AWAITING_VERIFICATION
    ).first()
    blocked = payable.payment_block_reason if payable.can_be_paid else None
    if not payable.can_be_paid or awaiting or blocked:
        return render(
            request, "payments/checkout_closed.html", {"payable": payable, "awaiting": awaiting, "blocked": blocked}
        )
    return _render_checkout(request, payable, kind, selected=request.GET.get("method"))


@login_required
@require_POST
def submit_manual(request, kind, reference, method):
    payable = get_user_payable_or_404(request.user, kind, reference)
    provider = get_provider_for_method(method)
    if not provider or not provider.is_manual or not provider.is_configured():
        raise Http404
    form = ManualPaymentForm(request.POST, request.FILES, provider=provider)
    if not form.is_valid():
        messages.error(request, "Please fix the highlighted fields and submit again.")
        return _render_checkout(request, payable, kind, selected=method, bound_form=form, status=400)
    try:
        submit_manual_payment(
            payable,
            request.user,
            provider,
            form.cleaned_data["provider_reference"],
            form.cleaned_data.get("proof_image"),
        )
    except PaymentError as exc:
        messages.error(request, str(exc))
        return redirect(f"{payable.get_payment_url()}?method={method}")
    messages.success(
        request,
        "Thanks! We received your payment details and will verify them shortly. "
        "You will get an email as soon as it is confirmed.",
    )
    return redirect(payable.get_absolute_url())


# --------------------------------------------------------------------------
# PayPal Orders API v2 (automated PayPal + Advanced Card Fields)
# --------------------------------------------------------------------------
def _json_body(request):
    try:
        data = json.loads(request.body or b"{}")
        return data if isinstance(data, dict) else None
    except (ValueError, UnicodeDecodeError):
        return None


@login_required
@require_POST
def paypal_create_order(request):
    """Create a PayPal order for a payable. Amount always comes from the database, never the browser."""
    data = _json_body(request)
    if data is None:
        return HttpResponseBadRequest("Invalid JSON")
    if not all(isinstance(data.get(key), str) for key in ("kind", "reference", "method")):
        return JsonResponse({"error": "Supply a valid kind, reference and payment method."}, status=400)
    provider = get_provider_for_method(data.get("method"))
    if not provider or provider.code not in ("paypal_checkout", "card_paypal") or not provider.is_configured():
        return JsonResponse({"error": "This payment method is not available."}, status=400)
    payable = get_user_payable_or_404(request.user, data.get("kind"), str(data.get("reference", "")))
    try:
        payment = start_automated_payment(payable, request.user, provider)
        if payment.provider_reference:
            return JsonResponse({"id": payment.provider_reference})
        if provider.code != "card_paypal":
            create = paypal_api.create_order
        elif data.get("cardButton") is True:  # Advanced Card Fields not offered for this account
            create = paypal_api.create_card_button_order
        else:
            create = paypal_api.create_card_order
        result = create(
            amount=payment.amount,
            currency=payment.currency,
            custom_id=str(payment.pk),
            invoice_id=f"{payable.reference}-{payment.pk}",
            description=payable.payable_label,
            request_id=f"create-{payment.idempotency_key}",
        )
    except PaymentError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except (paypal_api.PayPalError, requests.RequestException):
        logger.exception("PayPal create order failed")
        return JsonResponse({"error": "PayPal is not responding. Please try again in a minute."}, status=502)
    if not isinstance(result, dict) or not isinstance(result.get("id"), str) or not re.fullmatch(r"[A-Za-z0-9-]{1,100}", result["id"]):
        logger.error("PayPal returned an invalid order for payment %s", payment.pk)
        return JsonResponse({"error": "PayPal could not start checkout. Please try again shortly."}, status=502)
    Payment.objects.filter(pk=payment.pk).update(provider_reference=result["id"])
    return JsonResponse({"id": result["id"]})


@login_required
@require_POST
@transaction.atomic
def paypal_capture_order(request):
    data = _json_body(request)
    if data is None or not isinstance(data.get("orderID"), str) or not re.fullmatch(r"[A-Za-z0-9-]{1,100}", data["orderID"]):
        return HttpResponseBadRequest("Missing orderID")
    order_id = data["orderID"]
    payment = (
        Payment.objects.filter(provider_reference=order_id, customer=request.user, provider__in=GATEWAY_PROVIDERS)
        .first()
    )
    if not payment:
        return JsonResponse({"error": "Payment not found."}, status=404)
    # Keep this parent lock until the provider call is recorded. Another tab or
    # payment method cannot charge the same payable while capture is in flight.
    payment, payable = _lock_payment(payment.pk)
    if payment.status == Payment.Status.COMPLETED:  # double click / retry
        return JsonResponse({"status": "COMPLETED", "redirect": payable.get_absolute_url()})

    if payment.status == Payment.Status.AWAITING_VERIFICATION:
        return JsonResponse({"status": "PENDING", "redirect": payable.get_absolute_url()})
    if payment.status != Payment.Status.PENDING:
        return JsonResponse({"error": "This payment attempt is no longer active."}, status=400)
    try:
        _validate_payment_target(payment, payable)
        if Payment.objects.filter(**payment_filter(payable), status=Payment.Status.AWAITING_VERIFICATION).exclude(pk=payment.pk).exists():
            raise PaymentError("Another payment for this item is already being verified.")
    except PaymentError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    try:
        result = paypal_api.capture_order(order_id, request_id=f"capture-{payment.idempotency_key}")
    except paypal_api.PayPalError as exc:
        if exc.status_code and exc.status_code >= 500:
            return JsonResponse({"error": "PayPal could not confirm the result. Please retry this checkout shortly."}, status=502)
        mark_payment_failed(payment, exc.details, f"Capture failed: {exc}")
        declined = "DECLINED" in str(exc) or "INSTRUMENT" in str(exc)
        message = "Your card or PayPal payment was declined. Please try another method." if declined else "We could not confirm the payment. If you were charged, contact us with your receipt before trying again."
        return JsonResponse({"error": message}, status=402)
    except requests.RequestException:
        logger.exception("PayPal capture call failed for payment %s", payment.pk)
        return JsonResponse({"error": "PayPal is not responding. If you were charged, we will confirm it automatically."}, status=502)

    capture, unit = paypal_api.extract_capture(result)
    if not capture or result.get("id") != order_id or str(capture.get("custom_id") or unit.get("custom_id")) != str(payment.pk):
        mark_payment_failed(payment, result, "Capture response did not match this payment.")
        return JsonResponse({"error": "We could not verify this payment. Please contact us."}, status=400)

    capture_status = capture.get("status")
    if capture_status == "COMPLETED":
        try:
            complete_automated_payment(
                payment.pk, capture.get("id"), capture.get("amount", {}).get("value"), capture.get("amount", {}).get("currency_code"), result
            )
        except PaymentError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        messages.success(request, "Payment received. Thank you!")
        return JsonResponse({"status": "COMPLETED", "redirect": payable.get_absolute_url()})
    if capture_status == "PENDING":
        try:
            amount = capture.get("amount", {})
            received = Decimal(str(amount.get("value")))
            matches = received.is_finite() and received == payment.amount and amount.get("currency_code") == payment.currency
        except (InvalidOperation, TypeError, ValueError):
            matches = False
        if not matches or not isinstance(capture.get("id"), str) or not capture["id"] or len(capture["id"]) > 100:
            mark_payment_failed(payment, result, "Pending capture had an invalid amount or capture ID.")
            return JsonResponse({"error": "We could not verify this payment. Please contact us with your receipt."}, status=400)
        # e.g. eCheck or a PayPal review; the webhook will complete it later.
        Payment.objects.filter(pk=payment.pk).update(
            status=Payment.Status.AWAITING_VERIFICATION, capture_id=capture["id"], raw_response=result
        )
        messages.info(request, "PayPal is still processing your payment. We will email you once it clears.")
        return JsonResponse({"status": "PENDING", "redirect": payable.get_absolute_url()})
    mark_payment_failed(payment, result, f"Capture status {capture_status}")
    return JsonResponse({"error": "The payment was not completed. Please check your PayPal activity before trying again."}, status=402)


@csrf_exempt
@require_http_methods(["POST"])
def paypal_webhook(request):
    """PayPal webhook: verified with PayPal's signature API, stored once, then processed."""
    event = _json_body(request)
    if event is None or not isinstance(event.get("id"), str) or not event["id"] or len(event["id"]) > 100:
        return HttpResponseBadRequest()
    if not isinstance(event.get("event_type"), str) or not event["event_type"] or len(event["event_type"]) > 100 or not isinstance(event.get("resource"), dict):
        return HttpResponseBadRequest()
    if event["event_type"] == "PAYMENT.CAPTURE.COMPLETED" and not isinstance(event["resource"].get("amount"), dict):
        return HttpResponseBadRequest()
    if event["event_type"] in ("PAYMENT.CAPTURE.COMPLETED", "PAYMENT.CAPTURE.DENIED", "PAYMENT.CAPTURE.DECLINED") and not event["resource"].get("id"):
        return HttpResponseBadRequest()
    if event["event_type"] == "PAYMENT.CAPTURE.REFUNDED" and not _capture_id_from_links(event["resource"].get("links", [])):
        return HttpResponseBadRequest()
    if not paypal_api.is_configured() or not paypal_api.verify_webhook_signature(request.headers, event):
        logger.warning("Rejected PayPal webhook with invalid signature")
        return HttpResponse(status=400)

    try:
        with transaction.atomic():
            record, _created = WebhookEvent.objects.select_for_update().get_or_create(
                event_id=event["id"],
                defaults={"provider": "paypal", "event_type": event["event_type"], "payload": event},
            )
            if record.processed_at:
                return HttpResponse(status=200)
            if not _handle_paypal_event(record.payload):
                # PayPal retries non-2xx responses; don't permanently discard an
                # event that arrived before its local payment could be located.
                return HttpResponse(status=503)
            record.processed_at = timezone.now()
            record.save(update_fields=["processed_at"])
    except (paypal_api.PayPalError, requests.RequestException):
        logger.exception("PayPal webhook processing temporarily failed")
        return HttpResponse(status=503)
    return HttpResponse(status=200)


def _handle_paypal_event(event):
    event_type = event.get("event_type", "")
    resource = event.get("resource", {})
    if event_type == "PAYMENT.CAPTURE.COMPLETED":
        payment = _payment_for_capture(resource)
        if not payment:
            return False
        try:
            complete_automated_payment(
                payment.pk,
                resource.get("id", ""),
                resource["amount"].get("value", "0"),
                resource["amount"].get("currency_code", ""),
                event,
            )
        except PaymentError:
            logger.exception("Webhook could not complete payment %s", payment.pk)
    elif event_type in ("PAYMENT.CAPTURE.DENIED", "PAYMENT.CAPTURE.DECLINED"):
        payment = _payment_for_capture(resource)
        if not payment:
            return False
        mark_payment_failed(payment, event, f"PayPal: {event_type}")
    elif event_type == "PAYMENT.CAPTURE.REFUNDED":
        capture_id = _capture_id_from_links(resource.get("links", []))
        payment = Payment.objects.filter(capture_id=capture_id, provider__in=GATEWAY_PROVIDERS).first()
        if payment and payment.status == Payment.Status.REFUNDED:
            return True
        capture = paypal_api.get_capture(capture_id)
        if not payment:
            payment = _payment_for_capture(capture)
        if not payment:
            return False
        if capture.get("status") == "REFUNDED":
            record_gateway_refund(payment.pk, capture_id, event)
        elif capture.get("status") == "PARTIALLY_REFUNDED":
            payment, _payable = _lock_payment(payment.pk)
            payment.admin_notes = "\n".join(filter(None, [payment.admin_notes, "PayPal reported a partial refund. Download access remains active."]))
            payment.raw_response = event
            payment.save(update_fields=["admin_notes", "raw_response", "updated_at"])
            logger.warning("Payment %s partially refunded; full access remains active", payment.pk)
        else:
            return False
    return True


def _payment_for_capture(resource):
    """Some capture events omit custom_id but include an order or capture ID."""
    payments = Payment.objects.filter(provider__in=GATEWAY_PROVIDERS)
    custom_id = _int(resource.get("custom_id"))
    if custom_id:
        return payments.filter(pk=custom_id).first()
    capture_id = resource.get("id")
    if isinstance(capture_id, str) and capture_id:
        payment = payments.filter(capture_id=capture_id).first()
        if payment:
            return payment
    extra = resource.get("supplementary_data")
    related = extra.get("related_ids") if isinstance(extra, dict) else None
    order_id = related.get("order_id") if isinstance(related, dict) else None
    if isinstance(order_id, str) and order_id:
        return payments.filter(provider_reference=order_id).first()
    return None


def _int(value):
    try:
        result = int(value)
        return result if 0 < result <= 9223372036854775807 else None
    except (TypeError, ValueError):
        return None


def _capture_id_from_links(links):
    if not isinstance(links, list):
        return ""
    for link in links:
        if isinstance(link, dict) and link.get("rel") == "up" and isinstance(link.get("href"), str):
            capture_id = link["href"].rstrip("/").split("/")[-1]
            if re.fullmatch(r"[A-Za-z0-9-]{1,100}", capture_id):
                return capture_id
    return ""
