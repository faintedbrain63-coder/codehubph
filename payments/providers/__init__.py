"""Provider registry: picks which provider handles each payment method, based on settings."""

from django.conf import settings

from payments.providers.card_paypal import PayPalCardProvider
from payments.providers.card_stubs import PayMongoCardProvider, StripeCardProvider
from payments.providers.gcash_manual import GCashManualProvider
from payments.providers.gcash_paymongo import GCashPayMongoProvider
from payments.providers.paypal_checkout import PayPalCheckoutProvider
from payments.providers.paypal_manual import PayPalManualProvider

ALL_PROVIDERS = {
    p.code: p
    for p in (
        PayPalManualProvider(),
        PayPalCheckoutProvider(),
        GCashManualProvider(),
        GCashPayMongoProvider(),
        PayPalCardProvider(),
        PayMongoCardProvider(),
        StripeCardProvider(),
    )
}

METHOD_ORDER = ["paypal", "gcash", "card"]


def get_provider_for_method(method):
    if method == "paypal":
        return ALL_PROVIDERS["paypal_checkout" if settings.PAYPAL_MODE == "automated" else "paypal_manual"]
    if method == "gcash":
        return ALL_PROVIDERS["gcash_paymongo" if settings.GCASH_PROVIDER == "paymongo" else "gcash_manual"]
    if method == "card":
        return ALL_PROVIDERS.get(f"card_{settings.CARD_PROVIDER}", ALL_PROVIDERS["card_paypal"])
    return None


def get_checkout_providers():
    return [get_provider_for_method(m) for m in METHOD_ORDER]


def get_provider(code):
    return ALL_PROVIDERS.get(code)
