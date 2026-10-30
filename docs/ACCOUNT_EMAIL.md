# Account verification and recovery

New public registrations are inactive until the customer confirms ownership of their email address.
The signup request creates the account, legal acceptance record and delivery job in one transaction.
It does not sign the customer in. Existing accounts and staff-created accounts keep their current access.

## Yahoo SMTP

Keep these settings in the local, untracked `.env`, never in a template or committed file:

```dotenv
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.mail.yahoo.com
EMAIL_PORT=587
EMAIL_HOST_USER=your-full-address@yahoo.com
EMAIL_HOST_PASSWORD=your-yahoo-app-password
EMAIL_USE_TLS=True
EMAIL_USE_SSL=False
EMAIL_TIMEOUT=15
DEFAULT_FROM_EMAIL=CodehubPh <your-full-address@yahoo.com>
SITE_URL=https://codehubph.tech
PASSWORD_RESET_TIMEOUT=3600
EMAIL_VERIFICATION_TIMEOUT=86400
```

The SMTP username must be the full address belonging to the app password. Use that same address as
the sender. These host and port values follow [Yahoo's server settings](https://help.yahoo.com/kb/SLN28681.html).
Set `SITE_URL` to the real public origin, with no path or trailing query. Email links use
this configuration, never the incoming Host header. HTTPS is required outside DEBUG. Local development
can use `SITE_URL=http://127.0.0.1:8000`; those links work only on the developer's computer.

After updating settings, restart the web process and email worker.

## Start delivery

Apply the migration, then run a delivery worker alongside the web server:

```powershell
.\venv\Scripts\python.exe -E manage.py migrate
.\venv\Scripts\python.exe -E manage.py send_auth_emails --loop
```

On Linux use the virtual environment's Python executable. Run the worker under the same process supervisor
as Gunicorn, with the project directory as its working directory and the same environment. Use a separate
service with automatic restart. An example systemd unit, after substituting deployment paths and the
actual service account:

```ini
[Unit]
Description=CodehubPh account email delivery
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=simple
User=codehub
WorkingDirectory=/srv/codehubph
ExecStart=/srv/codehubph/venv/bin/python manage.py send_auth_emails --loop
Restart=on-failure
RestartSec=5
PrivateTmp=true
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
```

The web server queues requests and never waits for SMTP. **A worker must be running for account emails
to leave the queue.** To process a batch once, use `python manage.py send_auth_emails --limit 50`.
Jobs live in PostgreSQL, so web process restarts do not lose them. Multiple workers claim jobs using
row locks with `skip_locked`. Unfinished leases can be reclaimed after five minutes. Failures retry
with exponential backoff, up to six attempts. Delivery is at least once: a crash immediately after SMTP
acceptance can result in a duplicate email; verification and reset links still become invalid after use.

Django admin → **Auth email jobs** shows state, attempts and sanitized error class. Select failed jobs
and choose **Retry selected failed deliveries** after fixing SMTP configuration. Email addresses,
passwords and token URLs are not written into exception messages by the worker. Monitor failed jobs
and the age of pending jobs in deployment monitoring; SMTP acceptance does not guarantee inbox placement.
Delivered/cancelled/failed jobs and recipient addresses are removed after 30 days; rate counters expire
after a day. Jobs older than 24 hours are cancelled before sending.

## Customer flow and security

- Signup → check email → open link → press **Verify and activate account** → sign in. A GET does not
  activate an account, so mail scanners cannot consume the link. Verification expires after 24 hours
  by default. Confirmation is CSRF protected, locks the account row and cannot be replayed.
- A customer can request another verification link from sign-in or `/account/verify-email/resend/`.
  Unknown, disabled, already verified and throttled accounts receive the same acknowledgment.
- **Forgot your password?** → enter email → generic acknowledgment → open link → choose a valid new
  password → sign in. Only active eligible accounts with usable passwords receive reset messages.
  Django's signed reset tokens expire in one hour by default, invalidate after password change/login,
  and are removed from the reset form URL. Saving a new password invalidates old signed-in sessions.
- Database-backed limits allow three messages per address/purpose and 15 total requests per IP per
  15 minutes. Signup and verification resend share an address budget. The same limits apply regardless
  of whether an address exists. IP resolution uses the project's trusted-proxy rules. Do not enable
  `BEHIND_PROXY` when clients can directly reach the application server.
- Queued jobs contain an email snapshot and credential fingerprint, not tokens or message bodies.
  The worker cancels jobs when the address or password changed or the account is no longer eligible.
- Security forms do not load advertising scripts. Token pages prevent caching and use an origin-only
  referrer policy, keeping token paths out of referrers while preserving CSRF origin checks. Do not
  use `no-referrer` on these forms: browsers can send `Origin: null` and Django will reject the POST.
  Configure access logs and error-reporting tools to redact verification/reset URL tokens and never
  collect passwords or SMTP secrets. A recipient can always copy the plain-text fallback link.
- For accounts created through verified registration, the sign-in email is read-only in profile settings.
  Support must verify a requested address change before changing that identity. Legacy profile editing
  behavior remains available for accounts that predate mandatory verification.
- Signup does not create orders or submit project requests. A safe `next` destination and any existing
  purchase intent resume after verification and a normal password-based login in the same browser.

## Validation

```powershell
.\venv\Scripts\python.exe -E manage.py test accounts core.test_regressions --noinput
```

Automated tests use Django's in-memory email backend. They do not contact Yahoo or deliver customer emails.
For a live smoke test, use an address you control, run the worker and complete both signup and password reset.
Never use real customer addresses for test messages.
