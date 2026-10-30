# CodehubPh (`codehub_ph`)

A Django 5.2 project development service for custom **web applications, mobile applications and software**.
Clients include students working on capstone projects, local government units, military organizations and businesses.
Customers submit a brief, receive and accept a quote, pay, follow development and receive private deliverables.
Bootstrap 5.3 + vanilla JavaScript, PostgreSQL only.

| Area | URL |
| --- | --- |
| Public website | `/`, `/services/`, `/projects/request/` |
| Customer account | `/account/` (project requests, quotes, payments, deliveries, settings) |
| Admin portal (staff only) | `/manage/` |
| Django admin (superusers) | `/admin/` |

## Project layout

```
codehub_ph/            settings, root URLs, WSGI/ASGI
accounts/              custom User (email-only login), registration, profile, customer dashboard
catalog/               historical Product records; public product sales retired
orders/                historical Order/OrderItem records, invoices, secure paid downloads
capstone/              project services, custom briefs, quote/payment workflow, messages, private deliveries
payments/              Payment model, provider adapters, checkout, PayPal Orders API, webhooks
dashboard/             /manage/ admin portal (project services, requests, payments, customers, settings)
core/                  home/contact/legal pages, private storage, validators, emails, seed_demo command
templates/  static/    Bootstrap templates, app.css, app.js, checkout.js, dashboard.js
```

## Current service workflow

- **Start a project** (`/projects/request/`): register or sign in, select a client type and platform, then enter
  a title, school/organization, requirements and optional deadline. A student capstone also needs a course/program;
  organizational clients do not. A request can be submitted without an existing service listing.
- **Services** (`/services/`): browse service offerings and example projects, or submit a completely custom brief.
  Existing `/capstone/` bookmarks remain supported. Service listings do not require prebuilt source files.
- **Project workspace** (`/account/`): follow requests, review quotes, pay only after accepting a quote, message the
  team and download agreed deliverables after payment and upload. Payment by itself does not create project files.
- **Administration** (`/manage/`): publish services, review requests from every client group, quote, verify payments,
  upload customer builds and update delivery status. A request needs source deliverables before it can be marked delivered.
- **Retired product sales**: `PRODUCT_SALES_ENABLED=False` is the application default. Old product/cart/buy URLs
  return to Services. New product orders and payment attempts are blocked, including stale sign-in purchase intents.
  Existing receipts, paid downloads and payments already submitted before retirement remain supported. Records and
  private files are preserved. Legacy regression fixtures explicitly enable the old commerce backend for testing;
  `core.test_project_services` verifies the production service-only behavior.

Deploy this change with `python manage.py migrate`. The new request fields and nullable service reference preserve
existing project records; the default-tagline migration preserves other custom taglines.

## Portfolio projects and customer feedback

Open **Admin → Portfolio projects** (`/manage/portfolio/`) to create, edit, preview, publish or delete past/ongoing
projects. Web applications need a project/demo link to publish. Mobile applications and software need at least one
screenshot; up to 12 screenshots are supported, including optional previews for web apps. Entries can be featured and
classified as ongoing/completed. Published projects appear on the landing page and `/portfolio/`, with a detail page
for the link, full screenshots and approved customer feedback.

Choose **Edit introduction & profile** (`/manage/portfolio/presentation/`) to enter your portfolio heading,
introduction, name/studio, professional title, biography, expertise, location and optional code/professional profile
links. The developer profile is omitted when left blank. Landing-page visibility can be switched independently of
individual published projects. Staff see setup links on the landing page when the portfolio has no public content.

The landing page highlights the first featured project in a large visual layout, followed by a responsive project grid.
Web, mobile and software screenshots use matching display frames, with working project/live-site links and support for
light/dark themes and reduced motion. Optional case study fields include sector, contribution, project year, challenge,
solution and outcome. Only supplied details appear publicly; existing entries remain valid without them.

Optionally link a customer account or an existing service request. A linked request selects its own customer and
rejects a conflicting account. **My account → My reviews** lets only that customer submit or update a review for each
assigned project. Public display name, rating, comment and optional role are customer-controlled; a separate, initially
unchecked publication-permission checkbox is required and its server timestamp is stored. Reviews need staff approval
in **Customer comments** and edits return to pending. Project reviews for unpublished projects remain hidden even if
approved. General service reviews remain separate. Customer-authored project text cannot be rewritten through moderation.

Screenshots are stored privately and served through permission checks: unpublished screenshots are visible only to staff
and the linked customer. Project deletion removes its screenshots and associated portfolio reviews, while retaining the
linked service request and financial records. Replaced/deleted image files are cleaned up after successful database commits.

The older commerce instructions below document retained historical functionality, rather than the current sales offering.

## 1. Local setup (Windows / PowerShell)

Requires Python 3.12 and PostgreSQL 14 or newer.

```powershell
cd codehubph
py -3.12 -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env    # then edit the values (a ready-made .env is already included for local dev)
```

macOS/Linux: `python3.12 -m venv venv && source venv/bin/activate`.

> **Windows note:** if Python fails with `No module named 'encodings'`, a global `PYTHONHOME` variable is pointing at
> another Python install. Clear it for the session with `$env:PYTHONHOME=$null` (or remove it from the system
> environment variables) before activating the venv.

Nothing is installed globally; every dependency lives in `venv/` and is pinned in `requirements.txt`.

## 2. PostgreSQL

The app only runs on PostgreSQL. Create the database once:

```powershell
# using the PostgreSQL bin folder, e.g. C:\Program Files\PostgreSQL\14\bin
createdb -U postgres codehub_db
# or: psql -U postgres -c "CREATE DATABASE codehub_db;"
```

Connection settings are read from `.env`:

```
DB_NAME=codehub_db
DB_USER=postgres
DB_PASSWORD=root
DB_HOST=localhost
DB_PORT=5432
```

> `root` is a **local development** password only. In production create a dedicated database user with a strong,
> unique password, and never reuse the values from this repository.

If `migrate` fails with `connection refused` or `password authentication failed`, check that the PostgreSQL service
is running, that the port matches, and that the user/password in `.env` are correct.

## 3. Migrate, create an admin, seed demo data

```powershell
python manage.py migrate
python manage.py createsuperuser        # staff + superuser; can access /manage/ and /admin/
python manage.py seed_demo              # optional demo catalog
python manage.py runserver
```

`seed_demo` is idempotent and creates:

| Account | Email | Password |
| --- | --- | --- |
| Staff admin | `admin@example.com` | `Admin2026!` |
| Customer | `demo@example.com` | `Admin2026!` |

Only these two demo accounts receive the password. Existing accounts keep their passwords unless you pass
`--reset-all-passwords` (local development only). The command refuses to run when `DEBUG=False`, so the published
demo password can never be created on a live site.

It also creates 7 products (one left as Draft to show it is hidden from the store), 3 capstone projects with sample
files, 6 **sample** customer comments for the landing page, and a placeholder GCash number. **Change or delete the
demo accounts, and delete the sample comments in `/manage/testimonials/`, before going live.** Publishing invented
reviews on a real store misleads customers.

## Landing page, catalog and customer comments

- `/` is the landing page. It introduces the store and links into each category (Software, Mobile Apps,
  Capstone Projects) but does not list individual products. Web apps are offered as capstone projects (field
  "Web App / System"); old `/products/?category=web_app` links redirect to `/capstone/?field=web`.
- **Buying while signed out:** Buy now, cart checkout and "Request this project" send visitors to registration
  (with a "Sign in instead" option). After registering or signing in, checkout continues automatically: Buy now and
  cart checkout create the order and open the payment page, and capstone requests return to the request form. The
  pending purchase is kept in the session for one hour, so an abandoned attempt never creates an order later.
- **First-login tutorial:** new customers see a 4-step "How buying works" guide (choose, buy/cart/request, pay, get
  files). Finishing, skipping or closing it is saved on the account (`onboarding_completed_at`), and it can be
  replayed from **My account → How buying works**. Staff and accounts that had already signed in before this
  feature are not shown it.
- `/products/` is the catalog, the only page where products are listed. It has category tabs, search and sorting.
- **Customer comments** appear on the landing page under "What our customers say", with the average star rating.
  A customer can write one comment (1–5 stars) from **My account → My review** once a product order or capstone
  request has been paid. Every new or edited comment waits for staff review. In **/manage/testimonials/**, staff can
  approve, hide, feature (shown first), edit or delete comments, and can add comments that customers sent by email or
  chat. Comments from customer accounts are labelled "Verified customer".

Emails (order confirmations, payment approvals, password resets) print to the console by default. Set the `EMAIL_*`
values in `.env` to send real mail over SMTP.

New signups must verify their email before signing in. Verification and password-reset messages use a
durable delivery queue; run `python manage.py send_auth_emails --loop` alongside the web server.
See [account email setup](docs/ACCOUNT_EMAIL.md) for Yahoo SMTP, migrations, worker deployment and recovery.

## Admin catalog and uploads

Sign in with a staff account and open `/manage/` (**Admin portal** in the account menu), or use the **Store console**
link in `/admin/`. Both admin areas have sidebar navigation. The staff sidebar becomes a menu drawer on small screens;
Django admin exposes the same store-management shortcuts on its index and model pages.
Staff sign-ins now open `/manage/` automatically; existing `/account/` bookmarks also redirect staff to that workspace.
Customers continue to land on their personal dashboard. Staff can view their own purchases through **My purchases**
in the account menu (`/account/purchases/`). On narrow screens, select **Menu** to open the admin sidebar.

**Settings** in the admin sidebar (`/manage/settings/`) includes the signed-in admin's profile, password,
store name, public contact details and manual payment instructions. Customers use **My account → Settings**
(`/account/settings/`) to edit their own profile and password. Each section saves independently. Password changes
require the current password, validate the new password and keep the current device signed in. Store names update
throughout the storefront and receipts. The default brand is **CodehubPh**; migration `core.0004_codehubph_store_name`
also updates the previous FaintedBrain store name while preserving other custom names.

The staff console uses a dedicated workspace shell, separate from the storefront navbar, with grouped navigation,
real counts for payment/request/comment reviews and open support messages, and a **Global search** page. Search results
are staff-only, include drafts and are limited to five matches per section; open a section to see all matching records.
The overview has 7/14/30-day payment activity, exact daily amounts and links into each work queue. Payment activity is
not net accounting revenue: fully refunded payments are excluded, but partial refunds are not deducted.

List pages have visible search/filter labels, reset controls, result ranges and allowlisted page sizes (20/50/100).
Payments can be searched by email, order/request reference or transaction ID and filtered by method/status. Support
defaults to open messages, with searchable resolved/all views. Comment search and customer-history links are available.
Product/capstone editing includes **Save & continue editing**, a persistent save bar, linked validation summaries,
selected-file feedback and unsaved-change warnings. Add up to 12 screenshots from the product editor.

Storefront page containers use the available screen width with responsive edge padding, up to a 1920px layout; on
ultrawide screens the content is centred while section backgrounds stay full-bleed. Inside the container, long text,
legal documents (~75 characters per line), sign-in/registration, the password form and receipts keep a readable width,
and product/capstone card grids switch to 4 columns from 1700px. The staff content area still fills ultrawide screens
alongside its sidebar. Base storefront text is 18px, staff text 17px, and staff table text 16px, with
larger navigation/form/help text. The shared final overrides are in `static/css/layout.css`. The advanced Django admin
also has larger text and full-width page containers. Tables scroll within their panels on narrow screens.

- **Digital products** (`/manage/products/`): create, view, edit and delete software and mobile apps (list web apps as capstone projects). Search
  by name, slug, description or technologies; combine product-type/status filters and paginate the results.
- Choose **New product**, select the type, enter details/price, and upload a private digital file, optional thumbnail
  and gallery screenshots. Package source code in ZIP archives; mobile/desktop installer formats are supported.
  Upload limits and allowed extensions come from the existing `MAX_PRODUCT_FILE_MB`/`ALLOWED_*` settings and are
  enforced server-side. Use Draft to keep a listing hidden, or Published to make it available immediately.
- **Capstone → Projects** (`/manage/capstone/projects/`): searchable CRUD for capstone offerings, with field/status
  filters, private source-code uploads and optional documentation. Capstone projects retain their service workflow:
  customer request → quote → payment → delivery, separate from instant-download products.
- **View / Staff preview** works for published listings and drafts. Staff-only download links let administrators verify
  uploaded files; they do not expose public file URLs or consume customer download allowances.
- Deletion requires POST and CSRF protection. Listings referenced by orders/requests are moved to Draft instead of
  being deleted, preserving buyer records and download access. Never publish files you do not have permission to distribute;
  extension/size validation is not malware scanning.

[SweetAlert2](https://sweetalert2.github.io/) **11.26.25** is bundled locally under `static/vendor/sweetalert2/` with its
MIT license. Shared `static/js/alerts.js` handles Django notifications, form-error summaries, payment errors and action
confirmations across the storefront, staff console and Django admin. Confirmations preserve normal validation, CSRF,
file inputs and the clicked submit button. Errors/warnings require dismissal; routine success notices auto-dismiss.
Visible inline messages and browser confirmation remain fallbacks if the library fails to load. Inline field errors
remain available. SweetAlert2 does not require a runtime CDN request.

Bootstrap 5.3.3 and Bootstrap Icons 1.11.3 (including icon fonts and MIT licenses) are bundled locally too. Their downloaded
CSS/JS bytes were checked against the previously pinned SHA-384 hashes. No UI CDN is needed for core layout or controls.
Google Fonts remain optional, with system-font fallbacks. PayPal's hosted checkout still requires its provider scripts.

Customers can cancel unpaid orders from the order page (not while a payment is under review). An order that
contains a product the customer has since bought elsewhere cannot be paid. Checkout offers to cancel it and move
the remaining items back to the cart, so nobody is charged twice.

Customers can search their paginated purchase library, search/filter their own orders and project requests, and search
public capstone offerings by title or technology. A failed search shows reset guidance instead of saying no purchases
or requests exist. Library queries remain bounded as purchase history grows; payment/ownership/download rules are unchanged.

Accounts use email and password only. Existing accounts keep their email, password, permissions and purchase history
after `accounts.0003_email_only_login`; the old username column and its values are removed. An existing session may
require signing in again after deploying the authentication-backend change. Keep a database backup if you need to
recover historical usernames; rolling back the application does not restore removed username values.

## Registration agreements

Self-registration requires two unchecked-by-default agreements: the **Privacy Policy** and **Software License
Agreement and Terms of Service**. Both are enforced on the server, including requests made without JavaScript.
The account stores `legal_accepted_at`, `privacy_policy_version` and `license_agreement_version`, shown as read-only
fields in Django admin. Existing, demo and staff-created accounts are not falsely marked as having accepted.

The current documents are version **2026-10-24**, updated for custom development, developer ownership and paid scope
changes, client dependencies, limited support, lawful cancellation/indemnity/liability terms, and portfolio/review
publication. The privacy policy covers client-system processing roles, restricted data, retention for lawful claims,
and the actual Google AdSense integration. Registration acceptance does not authorize advertising personalization,
public client-data disclosure or mandatory-right waivers. The 2026-10-23 bodies and existing acceptance records remain
unchanged; existing users are not silently recorded as accepting the revision.

Current documents are at `/privacy/` and `/license/`; `/terms/` displays the same license/terms. Dated document URLs
under `/legal/<kind>/<version>/` keep published versions addressable. A stale registration form must be reloaded and
the current versions agreed to before account creation. Versions come from `core/legal.py`; preserve published bodies
and add a new version when legal text or the identified operator/contact changes.

Set the actual owner identity and contact details before public use:

```dotenv
LEGAL_OWNER_NAME=Your legal name or registered business name
LEGAL_CONTACT_ADDRESS=Your business/contact address
PRIVACY_CONTACT_EMAIL=privacy@your-domain.example
```

Until configured, the documents use the current site name and support email; an empty address is omitted. The
privacy agreement includes specific consent for educational details the customer chooses to supply for account/project
services; it does not grant marketing consent or waive privacy rights. Account/profile and capstone workflows still
need operational handling of data-subject requests, lawful retention, access permissions and consent withdrawal.

The license reserves rights for the operator/programmers, restricts redistribution and unlicensed deployments, defines
service scope, addresses payment/refund disputes, and includes qualified warranty/liability and indemnity terms.
Non-waivable rights and advertised commitments are preserved. These are drafted terms, not a legal-compliance
certification: have a Philippine lawyer review them, the actual business identity and operating practices before launch.
The draft was informed by the [Data Privacy Act](https://privacy.gov.ph/DATA-PRIVACY-ACT/),
[NPC guidance on educational information](https://privacy.gov.ph/wp-content/uploads/2022/01/Redacted-Advisory-Opinion-No.-2020-046.pdf),
[DTI refund guidance](https://fairtrade.dti.gov.ph/faq/is-no-return-no-exchange-policy-allowed/),
[Civil Code limits on contractual exclusions](https://elibrary.judiciary.gov.ph/thebookshelf/showdocs/2/53360),
and [copyright ownership rules](https://elibrary.judiciary.gov.ph/thebookshelf/showdocs/2/4371).
The revision also uses the [NPC outsourcing requirements](https://privacy.gov.ph/implementing-rules-regulations-data-privacy-act-2012/),
[Supreme Court guidance on commissioned copyright](https://elibrary.judiciary.gov.ph/thebookshelf/showdocs/16/67242)
and [Google's AdSense privacy-disclosure requirements](https://support.google.com/adsense/answer/1348695?hl=en).
This document update does not install a regional advertising consent-management platform or make an unconfigured
legal identity/contact valid; configure the actual owner/address/contact and review operational consent obligations before public use.

## 4. Payments

All payments, for product orders and capstone requests alike, go through one checkout page
(`/pay/<order|capstone>/<reference>/`) and one `Payment` model. Amounts are always computed on the server from the
order or the agreed capstone price, never from the browser.

### PayPal: manual mode (default)

```
PAYPAL_MODE=manual
PAYPAL_ME_URL=https://paypal.me/faintedbrain63
```

The checkout shows a PayPal.me button with the exact amount (for example
`https://paypal.me/faintedbrain63/2500.00PHP`). The customer pays, then submits the PayPal transaction ID (and an
optional screenshot). The order becomes **Awaiting verification** until staff approve or reject it under
`/manage/payments/`. On approval, downloads unlock and the customer is emailed. Rejection requires a reason, and the
customer can submit again.

The PayPal.me link can also be changed at runtime in **/manage/settings/**, which overrides `.env`.

### PayPal: automated mode (Orders API v2)

1. Create an app at <https://developer.paypal.com/dashboard/applications> (Sandbox first).
2. Set in `.env`:
   ```
   PAYPAL_MODE=automated
   PAYPAL_ENV=sandbox
   PAYPAL_CLIENT_ID=...
   PAYPAL_SECRET=...
   PAYPAL_WEBHOOK_ID=...
   ```
3. Add a webhook in the PayPal dashboard pointing to `https://<your-domain>/payments/webhooks/paypal/` with events
   `PAYMENT.CAPTURE.COMPLETED`, `PAYMENT.CAPTURE.DENIED`, `PAYMENT.CAPTURE.DECLINED` and `PAYMENT.CAPTURE.REFUNDED`,
   then copy its ID into `PAYPAL_WEBHOOK_ID`.

Flow: the browser renders PayPal Smart Buttons. The server creates the PayPal order (amount from the database,
`custom_id` = our payment ID, idempotency header), and the server captures it. A payment is marked paid only after the
capture response is verified for status, amount, currency and `custom_id`. Webhooks are signature-verified through
PayPal's `verify-webhook-signature` API and de-duplicated by event ID, so replays are ignored. If the amount
doesn't match, the payment is recorded as **Failed** and nothing unlocks.

**Going live:** set `PAYPAL_ENV=live`, replace the client ID, secret and webhook ID with the Live app's values, and
register the webhook again against the Live app. Test the whole flow once with a small real payment.

Run `python manage.py check_paypal --authenticate-only` to validate the saved API credentials without creating
an order or charge. Before deployment, run `python manage.py check_paypal --production --connect` against the
actual production settings. This checks live mode, secure hosting settings, authentication, webhook URL and
required event subscriptions. See [PayPal production setup](docs/PAYPAL_PRODUCTION.md).

### GCash

```
GCASH_PROVIDER=manual
```

Set the GCash account name, number and/or QR image in **/manage/settings/**. GCash is hidden at checkout until a
number or a QR code is configured. When a QR is set it is shown first, with a **Save QR image** button so customers
paying on their phone can use **Upload QR** in the GCash scanner; the number (if set) is offered as an alternative.
Static GCash/InstaPay QR codes carry no amount, so checkout tells the customer to type the exact amount. Customers pay in the GCash app, then submit the 13-digit reference number **and** a screenshot
(required). Staff verify the payment in `/manage/payments/`. The same reference number cannot be reused on another
payment.

`GCASH_PROVIDER=paymongo` is a documented adapter stub (`payments/providers/gcash_paymongo.py`). Implement PayMongo
Checkout Sessions plus its webhook there to automate GCash.

### Credit/debit cards (PCI approach)

```
CARD_PROVIDER=paypal
```

Card payments use **PayPal Advanced Card Fields**, available when PayPal API credentials are configured and the PayPal account is
eligible. The card number, expiry and CVV inputs are iframes hosted by PayPal. The card data goes straight from the
customer's browser to PayPal, and this application **never receives, stores, logs or processes** card numbers, CVV
or expiry dates. We keep only the PayPal order/capture IDs, the status and the amount. This keeps the site within the
lightest PCI DSS scope (SAQ A). 3-D Secure is requested when the issuer requires it.

If PayPal doesn't offer Advanced Card Fields for the merchant account (it is limited to certain countries, and
accounts in the Philippines are usually not eligible), checkout automatically shows PayPal's **Debit or Credit Card**
button instead. PayPal then collects the card in its own secure form, without the customer needing a PayPal account
(where PayPal supports guest card checkout). Both paths create the order with the server-side amount and are
captured and verified the same way.

To enable cards: create a REST app at developer.paypal.com → Apps & Credentials, then set `PAYPAL_CLIENT_ID` and
`PAYPAL_SECRET` in `.env` (sandbox first, `PAYPAL_ENV=live` with the Live app's keys when ready) and restart the app.
`PAYPAL_MODE` can stay `manual`; it only controls the PayPal tab. Test with PayPal's sandbox card generator.

When cards aren't configured, the card option is shown as "not available yet" with no input fields.
`CARD_PROVIDER=paymongo` and `CARD_PROVIDER=stripe` are adapter stubs for PayMongo or Stripe hosted payment fields.
They must also keep card data off this server.

### Refunds

Staff can mark a paid order or capstone request as **Refunded** in `/manage/`. This revokes download access and
records who did it and why. The money itself is returned from the PayPal or GCash account; the app doesn't call refund
APIs. In automated mode, a `PAYMENT.CAPTURE.REFUNDED` webhook also marks the payment refunded.

## 5. Files and downloads

- Product files, capstone sources/documentation, and payment proofs are stored in `private_media/` through
  `core.storage.PrivateMediaStorage`. That storage has **no public URL**. Files are streamed only by views that check
  login, ownership and paid status (and for products, the download limit and expiry).
- Thumbnails and gallery images are public in `media/`.
- Uploads are validated by extension and size (`MAX_PRODUCT_FILE_MB`, `MAX_IMAGE_MB`) and saved under random UUID
  names. Images are verified with Pillow.
- `DOWNLOAD_LIMIT` (default 10, `0` = unlimited) and `DOWNLOAD_EXPIRY_DAYS` (default 30, `0` = never) apply per
  purchased item. Staff can reset access from the order page.

## 6. Running the tests

```powershell
python manage.py test
```

Django creates a temporary `test_codehub_db` on the same PostgreSQL server, so the `.env` user needs the `CREATEDB`
privilege (the `postgres` superuser has it). Test uploads go to a temporary folder.

The Django test suite covers:

- **Authentication:** email-only registration/login, email normalization and uniqueness, lockout after 5 failures, logout, password reset, admin user management, and login-required pages.
- **Product visibility:** Draft products are hidden from the store, home, search and direct URLs, and appear once published.
- **Purchase access control:** unpaid, anonymous and other users cannot download; download limit and expiry; no public file URL; invoice ownership.
- **Payment approval:** PayPal.me amount link, no raw card inputs, GCash proof requirement, approval (idempotent), rejection and retry, duplicate references, refunds, and staff-only actions.
- **Automated PayPal (API mocked):** server-side amounts, capture verification, amount mismatch, webhook signature check, and webhook replay protection.
- **Capstone workflow:** request → quote → accept → pay → approve → in progress → delivered → completed; invalid transitions; cancel rules; owner-only access; staff-only quoting.
- **Admin portal:** staff-only access, all three product upload categories, product/capstone CRUD and search/filtering,
  draft previews, private staff downloads, file replacement, gallery edits, CSRF, protected deletion, navigation and settings.
- **Landing page and comments:** no product listings on the landing page, category tabs in the catalog, only approved comments shown (HTML-escaped), comments limited to paying customers, edits returning to review, and staff-only moderation.
- **Audit regressions:** checkout retries and current pricing, malformed payment payloads, full/partial/early PayPal refunds, case-insensitive email lockouts, unavailable payment methods, pagination, expired/missing downloads, and template rendering across the public/customer/staff areas.
- **Concurrent workflows:** real PostgreSQL connections verify simultaneous checkout reuse, download quotas, and approval/refund consistency.

## Admin AI assistant and app manual

Open **Settings → AI connection** (`/manage/settings/ai/`). Select Claude, OpenAI, Kimi,
DeepSeek, OpenRouter, GLM or MiniMax. The model is an editable text field. New connections
prefill the provider's verified frontier model, and **Use frontier default** restores that value.
Saved/custom model IDs stay intact; enter any valid model ID your API account supports.
The endpoint follows the provider/model. Enter an API key, choose **Use this connection for the admin chatbot**, then save.
Use **Test saved connection** to verify access. Model discovery displays IDs for reference for supported
providers without changing your text; GLM and MiniMax do not expose discovery here. Each provider retains its own encrypted
key and model. Only one connection powers the assistant at a time. No credentials are prefilled.

**AI chatbot** (`/manage/assistant/`) answers from the full [app manual](docs/ADMIN_MANUAL.md)
and live revenue aggregates. Staff can also read or download the manual from `/manage/manual/`.
Update that file when workflows change; it is read for each question. The assistant has no
write, SQL or code-execution tools. Conversation history stays in the authenticated server-side
session, limited to the latest six exchanges. New chat clears that session's history.

Revenue is calculated from payments currently marked Completed using `verified_at`, in
`TIME_ZONE` (Asia/Manila by default). Today/week/month/year are calendar-to-date, with weeks
starting Monday. Full refunds and all unconfirmed attempts are excluded, currencies stay
separate, and historical product receipts remain included. These are retained receipts before
fees/expenses, not profit or a complete cash-flow ledger. The app does not import AdSense earnings.
Independent cards display the authoritative totals alongside model replies.

Questions send the manual, revenue totals and recent messages to the selected external API.
The built-in context excludes customer identities, proofs, credentials and source files.
API use requires your provider's API key/access and may incur charges. No paid request occurs
just by loading a page. All external calls are mocked in automated tests.

Install the updated requirements and run `python manage.py migrate` when deploying. Keys use
Fernet encryption, with a purpose-specific key derived from `SECRET_KEY` by default. Optionally
set a dedicated `AI_CREDENTIAL_ENCRYPTION_KEY` before saving connections. Preserve the effective
encryption key with database backups; changing it requires re-entering provider keys. See
[provider protocols and operations](docs/AI_PROVIDERS.md) for official references and shared-cache
rate limiting considerations.

Run the frontend behavior tests (requires Node.js) with:

```powershell
node --test tests/frontend.test.cjs tests/alerts.test.cjs tests/manage.test.cjs tests/onboarding.test.cjs tests/assistant.test.cjs
```

If the machine has a conflicting global `PYTHONHOME`, invoke Python with `-E`, for example
`.\venv\Scripts\python.exe -E manage.py test --noinput`.

Optional isolated visual checks (Node.js 22+ and Chrome):

```powershell
.\venv\Scripts\python.exe -E -c "import os; os.environ['CODEHUB_RENDER_PREVIEW']='1'; os.environ.setdefault('DJANGO_SETTINGS_MODULE','codehub_ph.settings'); from django.core.management import execute_from_command_line; execute_from_command_line(['manage.py','test','dashboard.test_workspace.WorkspaceTests.test_workspace_shell_and_section_pages','--noinput'])"
.\venv\Scripts\python.exe -E -m http.server 8766 --bind 127.0.0.1 --directory .qa/site
# In a second terminal:
node tests/browser-render.cjs
```

Set `CHROME_BINARY` if Chrome is not at the default Windows installation path. These checks create fake snapshots in a
temporary test database, serve only `.qa/site` on localhost and launch a separate headless browser/profile. They never
authenticate to production or use the user's normal browser profile. Screenshots and results are generated under `.qa/`
(ignored by Git). Desktop/phone/ultrawide widths, dark mode, the mobile drawer, text sizes and overflow are checked.

The findings, design critique, changes, verification and remaining environment limitations are recorded in
[AUDIT.md](AUDIT.md).

Financial records (orders, payments, webhook events and capstone requests) are view-only in Django admin. Use
`/manage/` for workflow actions so state changes receive their checks, timestamps and notifications. Capstone quotes
and cancellation are frozen while a payment is under review. Full refunds revoke paid access; PayPal partial refunds
are recorded for staff review and keep access active. Before deploying these changes, run `migrate` and `collectstatic`
with the production environment loaded.

## 7. Production checklist

- [ ] `DEBUG=False`.
- [ ] A new, long, random `SECRET_KEY`:
      `python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"`.
- [ ] A dedicated PostgreSQL user with a **strong, unique password**. Never `postgres`/`root`.
- [ ] `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS=https://your-domain`, plus `SITE_URL=https://your-domain`.
- [ ] Serve over HTTPS. With `DEBUG=False` the app enables SSL redirect, secure cookies and HSTS; set
      `X-Forwarded-Proto` at the proxy.
- [ ] `python manage.py migrate` and `python manage.py collectstatic` (WhiteNoise serves `/static/`).
- [ ] Run Gunicorn (`gunicorn codehub_ph.wsgi:application`) behind Nginx. Nginx serves `/media/` from `media/`.
      **Never expose `private_media/`** through Nginx or any other public path.
- [ ] Configure Nginx and Cloudflare Tunnel as shown in **Deploying behind Nginx + Cloudflare Tunnel** below.
- [ ] Schedule `python manage.py cleanup_uploads` (e.g. hourly) to remove abandoned partial uploads.
- [ ] Configure real SMTP (`EMAIL_*`) so customers receive payment and delivery emails.
- [ ] Configure payments: PayPal Live credentials and webhook if automated, and the GCash number/QR in `/manage/settings/`.
- [ ] Remove or change the `seed_demo` accounts, and delete the sample customer comments.
- [ ] Back up the database **and** both media folders.
- [ ] `python manage.py check --deploy` reports no issues.

### Deploying behind Nginx + Cloudflare Tunnel

Request path: browser → Cloudflare (HTTPS) → `cloudflared` → Nginx (`127.0.0.1:80`) → Gunicorn (`127.0.0.1:8000`).

**Large uploads are chunked.** Cloudflare refuses request bodies over 100 MB (Free/Pro plans), but product and
capstone files may be up to `MAX_PRODUCT_FILE_MB` (500 MB). In `/manage/`, the product file, capstone source code,
capstone documentation and per-request deliverables are therefore sent from the browser in `UPLOAD_CHUNK_MB`
pieces (default 8 MB) to `/manage/uploads/`. The form is saved only after every chunk has arrived, and the
assembled file is checked by the same extension/size validators and moved into `private_media/`. Progress is shown
under each file field, with a **Cancel upload** link. Dropped connections are retried automatically. If the
upload still fails, select **Save** again with the same file and it resumes from the last stored byte. After a
validation error, an uploaded file is kept and does not need to be uploaded again. Partial files live in
`private_media/chunked/` and expire after `UPLOAD_SESSION_HOURS` (default 24). Uploads in the advanced Django admin
(`/admin/`) are not chunked, so use `/manage/` for files over ~90 MB.

Nginx site (adjust paths and domain):

```nginx
# cloudflared connects from this machine; trust it for the visitor's real IP.
set_real_ip_from 127.0.0.1;
set_real_ip_from ::1;
real_ip_header CF-Connecting-IP;

server {
    listen 127.0.0.1:80;
    server_name store.example.com;

    # Chunks are UPLOAD_CHUNK_MB (8 MB); product forms with 12 screenshots stay well below this.
    # Cloudflare's own 100 MB limit applies regardless.
    client_max_body_size 100m;

    location /media/ { alias /srv/codehub_ph/media/; }   # public images only
    # Never add a location for private_media/.

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        # Pass Cloudflare's "https" through. Using $scheme here would send "http" and cause a redirect loop.
        proxy_set_header X-Forwarded-Proto $http_x_forwarded_proto;
        # Overwrite (do not append) so visitors cannot spoof the address used for login lockouts and rate limits.
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 180s;
        proxy_send_timeout 180s;
    }
}
```

`cloudflared` ingress (`config.yml`):

```yaml
tunnel: <your-tunnel-id>
credentials-file: /etc/cloudflared/<your-tunnel-id>.json
ingress:
  - hostname: store.example.com
    service: http://127.0.0.1:80
  - service: http_status:404
```

Gunicorn: `gunicorn codehub_ph.wsgi:application --bind 127.0.0.1:8000 --workers 3 --timeout 120`. An 8 MB
chunk finishes well within the timeout even on slow connections. If uploads report "The server rejected the chunk
size" (HTTP 413), raise `client_max_body_size` or lower `UPLOAD_CHUNK_MB`. Set
`ALLOWED_HOSTS=store.example.com`, `CSRF_TRUSTED_ORIGINS=https://store.example.com` and
`SITE_URL=https://store.example.com`, and `BEHIND_PROXY=True` so login lockouts and the contact-form limit see each
visitor's real IP instead of `127.0.0.1` (only safe because Gunicorn listens on `127.0.0.1`). Keep `SECURE_SSL_REDIRECT=True`; Cloudflare supplies HTTPS. Keep
`private_media/` on the same disk as `private_media/chunked/` so finished uploads are moved, not copied.

## 8. Defaults chosen

These points were not specified in the brief, so these defaults were used:

- **Currency:** PHP (₱), shown with two decimals. Change it with `CURRENCY` / `CURRENCY_SYMBOL`.
- **Order numbers:** `FB-XXXXXXXX`; capstone references: `CAP-XXXXXX` (random, non-sequential).
- **Downloads:** 10 downloads within 30 days of payment, per item.
- **Capstone files** unlock once the request is **Paid**. Admins can upload customized deliverables per request,
  which take priority over the project's base files.
- **Re-quoting** is allowed while a request is Quoted or Accepted (before payment).
- **Cancellation:** customers can cancel until payment; staff can cancel any unpaid request.
- **Login:** email is the sole account identifier; there is no separate username. Email addresses are trimmed, stored in lowercase and unique without regard to case. `createsuperuser` asks for email rather than username.
- **Login lockout:** 5 failed attempts per normalized email + IP lock that combination for 30 minutes (django-axes).
- **Buy Now and cart checkout** reuse an identical unpaid order at current product prices instead of creating duplicates.
- **Refunds** are recorded manually (see above).
- The **demo GCash number** set by `seed_demo` is a placeholder, so replace it before accepting payments.
