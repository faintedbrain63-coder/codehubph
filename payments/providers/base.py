"""Base class for payment providers.

A provider is one way to collect money for a payment method (the tabs on the
checkout page). To add a gateway, subclass PaymentProvider, give it a unique
`code`, and select it in providers/__init__.py from a setting. Checkout views
and templates do not need to change.
"""


class PaymentProvider:
    code = ""  # stored on Payment.provider, e.g. "gcash_manual"
    method = ""  # Payment.Method value, e.g. "gcash"
    label = ""
    icon = ""  # Bootstrap Icons name
    description = ""
    is_manual = False  # manual providers need admin verification
    panel_template = "payments/panels/unavailable.html"

    def is_configured(self):
        return True

    def get_panel_context(self, request, payable):
        return {}


class ManualProvider(PaymentProvider):
    """Customer pays outside the site, then submits a reference number (and proof)."""

    is_manual = True
    requires_proof = False
    reference_label = "Reference number"
    reference_help = ""
    proof_label = "Screenshot of your receipt"


class GatewayProvider(PaymentProvider):
    """Payment is confirmed by the gateway's API (server-side), not by an admin."""

    is_manual = False
    uses_paypal_sdk = False
