from payments.providers import paypal_api
from payments.providers.base import GatewayProvider


class PayPalCheckoutProvider(GatewayProvider):
    """Automated PayPal Checkout (Orders API v2). Enabled with PAYPAL_MODE=automated."""

    code = "paypal_checkout"
    method = "paypal"
    label = "PayPal"
    icon = "paypal"
    description = "Pay with your PayPal balance or a linked card. Confirmed instantly."
    panel_template = "payments/panels/paypal_checkout.html"
    uses_paypal_sdk = True

    def is_configured(self):
        return paypal_api.is_configured()
