from django.conf import settings

from core.models import SiteSettings, VisitorCounter
from core.legal import get_document
from payments.providers import get_checkout_providers
from orders.models import Order


def site(request):
    site_settings = SiteSettings.load()
    providers = [p for p in get_checkout_providers() if p.is_configured()]
    labels = [p.label for p in providers]
    methods_text = ", ".join(labels[:-1]) + " and " + labels[-1] if len(labels) > 1 else (labels[0] if labels else "the methods available at checkout")
    return {
        "site": site_settings,
        "SITE_NAME": site_settings.name,
        "visitor_count": VisitorCounter.current(),
        "PRODUCT_SALES_ENABLED": settings.PRODUCT_SALES_ENABLED,
        "has_order_history": request.user.is_authenticated and Order.objects.filter(user=request.user).exists(),
        "CURRENCY": settings.CURRENCY,
        "CURRENCY_SYMBOL": settings.CURRENCY_SYMBOL,
        "available_payment_providers": providers,
        "payment_methods_text": methods_text,
        "payment_method_count": len(providers),
        "available_payment_methods": {p.method for p in providers},
        # Gateway payments unlock downloads immediately; manual ones wait for staff verification.
        "has_instant_payments": any(not p.is_manual for p in providers),
        "legal_owner_name": settings.LEGAL_OWNER_NAME or site_settings.name,
        "legal_contact_address": settings.LEGAL_CONTACT_ADDRESS,
        "privacy_contact_email": settings.PRIVACY_CONTACT_EMAIL or site_settings.contact_email,
        "privacy_document": get_document("privacy"),
        "license_document": get_document("license"),
    }
