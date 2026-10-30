"""Transactional emails. Templates live in templates/emails/<name>.txt.

Sending never breaks a request: failures are logged so a flaky SMTP server
cannot block an order or a payment approval.
"""

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

from core.models import SiteSettings

logger = logging.getLogger(__name__)


def send_templated_email(subject, template, context, recipients):
    recipients = [r for r in recipients if r]
    if not recipients:
        return
    try:
        site = SiteSettings.load()
        full_context = {
            "site_name": site.name,
            "site": site,
            "site_url": settings.SITE_URL,
            "currency": settings.CURRENCY,
            **context,
        }
        body = render_to_string(f"emails/{template}.txt", full_context)
        send_mail(f"[{site.name}] {subject}", body, settings.DEFAULT_FROM_EMAIL, recipients)
    except Exception:  # noqa: BLE001 - email must never break the main flow
        logger.exception("Could not send email %s to %s", template, recipients)


def _admin_recipients():
    return [SiteSettings.load().contact_email]


def notify_order_received(order):
    send_templated_email(
        f"Order {order.number} received", "order_received", {"order": order}, [order.user.email]
    )


def notify_payment_submitted(payment):
    """Tells the owner that a manual payment is waiting for verification."""
    send_templated_email(
        f"Payment to verify: {payment.payable.reference}",
        "admin_payment_submitted",
        {"payment": payment, "payable": payment.payable},
        _admin_recipients(),
    )


def notify_payment_approved(payment):
    send_templated_email(
        f"Payment confirmed for {payment.payable.reference}",
        "payment_approved",
        {"payment": payment, "payable": payment.payable},
        [payment.customer.email],
    )


def notify_payment_rejected(payment):
    send_templated_email(
        f"Action needed: payment for {payment.payable.reference}",
        "payment_rejected",
        {"payment": payment, "payable": payment.payable},
        [payment.customer.email],
    )


def notify_download_access_reset(order):
    send_templated_email(
        f"Your downloads for {order.number} are ready", "download_ready", {"order": order}, [order.user.email]
    )


def notify_capstone_status(capstone_request):
    send_templated_email(
        f"Project request {capstone_request.reference}: {capstone_request.get_status_display()}",
        "capstone_status",
        {"req": capstone_request},
        [capstone_request.customer.email],
    )


def notify_admin_capstone(capstone_request, event):
    send_templated_email(
        f"Project request {capstone_request.reference}: {event}",
        "admin_capstone_event",
        {"req": capstone_request, "event": event},
        _admin_recipients(),
    )
