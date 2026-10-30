"""Minimal PayPal REST client for Orders API v2 and webhook signature verification.

Only IDs and amounts travel through this module. Card numbers are entered in
PayPal-hosted fields in the browser and never reach our server.
"""

import logging
import hashlib
from decimal import Decimal

import requests
from django.conf import settings
from django.core.cache import cache

from core.models import SiteSettings

logger = logging.getLogger("payments")

TIMEOUT = 20


class PayPalError(Exception):
    def __init__(self, message, status_code=None, details=None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details or {}


def is_configured():
    return bool(settings.PAYPAL_CLIENT_ID and settings.PAYPAL_SECRET)


def base_url():
    if settings.PAYPAL_ENV == "live":
        return "https://api-m.paypal.com"
    return "https://api-m.sandbox.paypal.com"


def _access_token():
    identity = hashlib.sha256(f"{settings.PAYPAL_CLIENT_ID}:{settings.PAYPAL_SECRET}".encode()).hexdigest()
    cache_key = f"paypal_token_{settings.PAYPAL_ENV}_{identity}"
    token = cache.get(cache_key)
    if token:
        return token
    response = requests.post(
        f"{base_url()}/v1/oauth2/token",
        auth=(settings.PAYPAL_CLIENT_ID, settings.PAYPAL_SECRET),
        data={"grant_type": "client_credentials"},
        timeout=TIMEOUT,
    )
    if response.status_code != 200:
        raise PayPalError("Could not authenticate with PayPal.", response.status_code)
    try:
        data = response.json()
    except ValueError as exc:
        raise PayPalError("PayPal returned an invalid authentication response.", 502) from exc
    if not isinstance(data, dict) or not isinstance(data.get("access_token"), str) or not data["access_token"]:
        raise PayPalError("PayPal did not return an access token.", 502)
    try:
        lifetime = max(int(data.get("expires_in", 3600)) - 120, 1)
    except (TypeError, ValueError, OverflowError):
        lifetime = 60
    cache.set(cache_key, data["access_token"], lifetime)
    return data["access_token"]


def _request(method, path, json=None, request_id=None):
    headers = {
        "Authorization": f"Bearer {_access_token()}",
        "Content-Type": "application/json",
        # Capture verification needs purchase units, amounts and capture IDs.
        "Prefer": "return=representation",
    }
    if request_id:
        # PayPal-Request-Id makes create/capture idempotent: retries return the original result.
        headers["PayPal-Request-Id"] = request_id
    response = requests.request(method, f"{base_url()}{path}", json=json, headers=headers, timeout=TIMEOUT)
    try:
        data = response.json()
    except ValueError:
        data = {}
    if not isinstance(data, dict):
        raise PayPalError("PayPal returned an invalid response.", 502)
    if response.status_code >= 400:
        issue = ""
        if isinstance(data.get("details"), list) and data["details"] and isinstance(data["details"][0], dict):
            issue = data["details"][0].get("issue", "")
        logger.warning("PayPal %s %s failed: %s %s", method, path, response.status_code, issue or data.get("name"))
        raise PayPalError(issue or data.get("message") or "PayPal request failed.", response.status_code, data)
    return data


def create_order(*, amount: Decimal, currency, custom_id, invoice_id, description, request_id):
    payload = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "reference_id": invoice_id,
                "custom_id": custom_id,
                "invoice_id": invoice_id,
                "description": description[:127],
                "amount": {"currency_code": currency, "value": f"{amount:.2f}"},
            }
        ],
        "payment_source": {
            "paypal": {
                "experience_context": {
                    "shipping_preference": "NO_SHIPPING",
                    "user_action": "PAY_NOW",
                    "brand_name": SiteSettings.load().name[:127],
                }
            }
        },
    }
    return _request("POST", "/v2/checkout/orders", json=payload, request_id=request_id)


def create_card_button_order(*, amount: Decimal, currency, custom_id, invoice_id, description, request_id):
    """Order for the PayPal "Debit or Credit Card" button, used where Advanced Card Fields isn't offered
    (for example, merchant accounts in the Philippines). PayPal hosts the card form in its own window."""
    payload = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "reference_id": invoice_id,
                "custom_id": custom_id,
                "invoice_id": invoice_id,
                "description": description[:127],
                "amount": {"currency_code": currency, "value": f"{amount:.2f}"},
            }
        ],
        "application_context": {
            "shipping_preference": "NO_SHIPPING",
            "user_action": "PAY_NOW",
            "brand_name": SiteSettings.load().name[:127],
        },
    }
    return _request("POST", "/v2/checkout/orders", json=payload, request_id=request_id)


def create_card_order(*, amount: Decimal, currency, custom_id, invoice_id, description, request_id):
    """Order used by Advanced Card Fields; 3-D Secure is requested when the card requires it."""
    payload = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "reference_id": invoice_id,
                "custom_id": custom_id,
                "invoice_id": invoice_id,
                "description": description[:127],
                "amount": {"currency_code": currency, "value": f"{amount:.2f}"},
            }
        ],
        "payment_source": {
            "card": {"attributes": {"verification": {"method": "SCA_WHEN_REQUIRED"}}}
        },
    }
    return _request("POST", "/v2/checkout/orders", json=payload, request_id=request_id)


def capture_order(order_id, request_id):
    return _request("POST", f"/v2/checkout/orders/{order_id}/capture", json={}, request_id=request_id)


def get_order(order_id):
    return _request("GET", f"/v2/checkout/orders/{order_id}")


def get_capture(capture_id):
    return _request("GET", f"/v2/payments/captures/{capture_id}")


def extract_capture(order_data):
    """Return (capture dict, purchase unit dict) from an Orders API response, or (None, None)."""
    if not isinstance(order_data, dict) or not isinstance(order_data.get("purchase_units"), list):
        return None, None
    for unit in order_data["purchase_units"]:
        if not isinstance(unit, dict) or not isinstance(unit.get("payments"), dict):
            continue
        captures = unit.get("payments", {}).get("captures", [])
        if isinstance(captures, list) and captures and isinstance(captures[0], dict) and isinstance(captures[0].get("amount"), dict):
            return captures[0], unit
    return None, None


def verify_webhook_signature(headers, event):
    """Ask PayPal to verify a webhook. Returns True only for verification_status == SUCCESS."""
    if not settings.PAYPAL_WEBHOOK_ID:
        logger.error("PAYPAL_WEBHOOK_ID is not set; rejecting webhook.")
        return False
    payload = {
        "auth_algo": headers.get("PAYPAL-AUTH-ALGO", ""),
        "cert_url": headers.get("PAYPAL-CERT-URL", ""),
        "transmission_id": headers.get("PAYPAL-TRANSMISSION-ID", ""),
        "transmission_sig": headers.get("PAYPAL-TRANSMISSION-SIG", ""),
        "transmission_time": headers.get("PAYPAL-TRANSMISSION-TIME", ""),
        "webhook_id": settings.PAYPAL_WEBHOOK_ID,
        "webhook_event": event,
    }
    if not all(payload[k] for k in ("auth_algo", "cert_url", "transmission_id", "transmission_sig", "transmission_time")):
        return False
    try:
        result = _request("POST", "/v1/notifications/verify-webhook-signature", json=payload)
    except (PayPalError, requests.RequestException):
        logger.exception("Webhook signature verification call failed")
        return False
    return result.get("verification_status") == "SUCCESS"
