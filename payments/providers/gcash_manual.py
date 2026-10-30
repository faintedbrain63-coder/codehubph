from core.models import SiteSettings
from payments.providers.base import ManualProvider


class GCashManualProvider(ManualProvider):
    """Customer sends money to the store's GCash number and uploads the receipt."""

    code = "gcash_manual"
    method = "gcash"
    label = "GCash"
    icon = "phone"
    description = "Send money via GCash, then upload your receipt."
    panel_template = "payments/panels/gcash_manual.html"
    requires_proof = True
    reference_label = "GCash reference number"
    reference_help = "The 13-digit Ref No. shown on your GCash receipt."

    def is_configured(self):
        return SiteSettings.load().gcash_ready

    def get_panel_context(self, request, payable):
        return {"gcash": SiteSettings.load()}
