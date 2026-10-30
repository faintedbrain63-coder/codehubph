from core.models import SiteSettings
from payments.providers.base import ManualProvider


class PayPalManualProvider(ManualProvider):
    """Default PayPal mode: customer pays through PayPal.me, then submits the transaction ID.

    A PayPal.me link cannot notify our server, so an admin verifies each payment.
    """

    code = "paypal_manual"
    method = "paypal"
    label = "PayPal"
    icon = "paypal"
    description = "Pay with your PayPal balance or a linked card."
    panel_template = "payments/panels/paypal_manual.html"
    reference_label = "PayPal transaction ID"
    reference_help = "Found in the PayPal receipt email or under Activity in the PayPal app (17 characters)."

    def is_configured(self):
        return bool(SiteSettings.load().paypal_link)

    def get_panel_context(self, request, payable):
        site = SiteSettings.load()
        return {"paypal_url": f"{site.paypal_link}/{payable.amount_due:.2f}{payable.currency}"}
