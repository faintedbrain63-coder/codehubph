"""Alternative card gateway adapters (stubs).

Both follow the same rule as PayPal Advanced Card Fields: card data is
collected by the gateway's own JavaScript component, and our server only
receives a token / intent ID.

PayMongo (CARD_PROVIDER=paymongo):
  - Server: create a Payment Intent (amount in centavos) after
    services.start_automated_payment(); return its client_key.
  - Browser: create a payment method with PayMongo.js and attach it to the intent.
  - Webhook: verify the Paymongo-Signature HMAC, then complete_automated_payment().

Stripe (CARD_PROVIDER=stripe):
  - Server: create a PaymentIntent with metadata={"payment_id": payment.pk}; return client_secret.
  - Browser: mount Stripe Elements (Payment Element) and call stripe.confirmPayment().
  - Webhook: verify with stripe.Webhook.construct_event(body, sig_header, STRIPE_WEBHOOK_SECRET)
    and handle payment_intent.succeeded -> complete_automated_payment().
"""

from payments.providers.base import GatewayProvider


class PayMongoCardProvider(GatewayProvider):
    code = "card_paymongo"
    method = "card"
    label = "Debit / Credit Card"
    icon = "credit-card"
    description = "Visa and Mastercard via PayMongo."

    def is_configured(self):
        return False


class StripeCardProvider(GatewayProvider):
    code = "card_stripe"
    method = "card"
    label = "Debit / Credit Card"
    icon = "credit-card"
    description = "All major cards via Stripe."

    def is_configured(self):
        return False
