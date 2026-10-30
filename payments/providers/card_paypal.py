from payments.providers import paypal_api
from payments.providers.base import GatewayProvider


class PayPalCardProvider(GatewayProvider):
    """Debit/credit cards through PayPal Advanced Card Fields.

    Card number, expiry and CVV are typed into iframes hosted by PayPal. Our
    server only sees a PayPal order ID, which keeps it out of PCI DSS card-data
    scope (SAQ A). The order is captured and verified server-side.
    """

    code = "card_paypal"
    method = "card"
    label = "Debit / Credit Card"
    icon = "credit-card"
    description = "Visa, Mastercard, American Express and more."
    panel_template = "payments/panels/card_paypal.html"
    uses_paypal_sdk = True

    def is_configured(self):
        return paypal_api.is_configured()
