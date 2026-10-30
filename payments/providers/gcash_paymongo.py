"""Adapter stub for automated GCash through PayMongo (or Xendit).

How to finish it later (checkout views and templates stay the same):
1. Add PAYMONGO_SECRET_KEY / PAYMONGO_WEBHOOK_SECRET to .env and settings.py.
2. In a JSON view, call payments.services.start_automated_payment(), then create a
   PayMongo Payment Intent with payment_method_allowed=["gcash"] and redirect the
   customer to the returned checkout URL.
3. Add a webhook view that verifies the `Paymongo-Signature` header (HMAC-SHA256 of
   "<timestamp>.<raw body>" with the webhook secret, compared with hmac.compare_digest),
   stores the event in WebhookEvent, then calls services.complete_automated_payment().
4. Set GCASH_PROVIDER=paymongo.
"""

from payments.providers.base import GatewayProvider


class GCashPayMongoProvider(GatewayProvider):
    code = "gcash_paymongo"
    method = "gcash"
    label = "GCash"
    icon = "phone"
    description = "Pay instantly with GCash."

    def is_configured(self):
        return False  # not implemented yet; checkout shows the "unavailable" panel
