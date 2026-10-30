# PayPal production setup

PayPal uses separate credentials for sandbox and live environments. Production requests must use the
Live app's credentials and the live API endpoint; see [PayPal's production guide](https://developer.paypal.com/api/rest/production/).
Pasting credentials alone does not switch the application out of manual or sandbox mode.

Configure the **production server's** environment (keep development on localhost separate):

```dotenv
PAYPAL_MODE=automated
PAYPAL_ENV=live
PAYPAL_CLIENT_ID=<live-app-client-id>
PAYPAL_SECRET=<live-app-secret>
PAYPAL_WEBHOOK_ID=<live-app-webhook-id>
DEBUG=False
SITE_URL=https://your-public-domain.example
ALLOWED_HOSTS=your-public-domain.example
CSRF_TRUSTED_ORIGINS=https://your-public-domain.example
SECURE_SSL_REDIRECT=True
```

The secret stays on the server; only the public client ID is included in the PayPal JavaScript SDK URL.
Keep `.env` untracked. Restart the web processes and email worker after changing environment settings.
Preserve the existing secret key and database credentials when updating a deployed environment.

## Register the webhook

In the PayPal developer dashboard, open the **Live** app corresponding to the credentials and register:

```text
https://your-public-domain.example/payments/webhooks/paypal/
```

Subscribe to `PAYMENT.CAPTURE.COMPLETED`, `PAYMENT.CAPTURE.DENIED`,
`PAYMENT.CAPTURE.DECLINED` and `PAYMENT.CAPTURE.REFUNDED`. Save the returned webhook ID as
`PAYPAL_WEBHOOK_ID`. Sandbox webhook registrations do not replace the live registration.
See [PayPal's webhook integration documentation](https://developer.paypal.com/api/rest/webhooks/rest/).

The HTTPS endpoint must be reachable from the internet without login, browser challenges or proxy redirects.
Only this webhook route is CSRF-exempt; its payload is verified using PayPal's signature verification API.
The application checks account ownership and database amounts on checkout, captures on the server,
validates capture amount/currency/payment identity and deduplicates webhook events. Invalid signatures
are rejected. The receiver never trusts a client-side “payment successful” message as proof of payment.

## Verify without charging

```powershell
# OAuth only; useful before the public webhook exists. No payment is created.
.\venv\Scripts\python.exe -E manage.py check_paypal --authenticate-only

# On the production server, with its real secure settings:
python manage.py check --deploy
python manage.py check_paypal --production --connect
```

The production command requires live API mode, credentials, webhook ID, public HTTPS `SITE_URL`, explicit
allowed host and CSRF origin, `DEBUG=False`, and secure session/CSRF cookies. The network check authenticates
and reads webhook metadata to confirm its URL and events. It never creates an order, captures a payment,
issues a refund, changes PayPal settings or prints credentials/access tokens. Invalid `PAYPAL_ENV` values
fail closed rather than silently selecting sandbox.

A successful preflight verifies configuration and authentication, not a completed payment. After deploying,
perform an explicitly authorized live checkout with a separate eligible buyer account and verify that
the captured payment reaches the correct merchant and the matching local project/order becomes paid.
Do not use the merchant account to pay itself. Advanced card fields and guest card options depend on
PayPal merchant/buyer eligibility; the existing card-button fallback does not guarantee universal availability.

For a failed OAuth check, confirm that both values are saved in the server's `.env`, belong to the same
**Live** app, and are not overridden by process environment variables. The production host needs outbound
HTTPS access to `api-m.paypal.com`. A missing webhook ID blocks asynchronous completion and refund updates
even when direct browser capture succeeds; configure it before accepting production payments.
