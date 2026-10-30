# Build Plan: `codehub_ph` (FaintedBrain Digital Store)

This plan follows `capstone_marketplace_prompt.md` section by section. The build order matches section 10:
project setup -> accounts -> catalog -> landing page -> orders -> payments -> capstone service -> admin portal -> tests -> README.

---

## 0. Environment findings (checked before planning)

| Item | Finding | Decision |
|---|---|---|
| Python | `python` is not on PATH; `py -V:Astral/CPython3.12.14` is available | Create the venv with Python 3.12.14 (prompt requires 3.12+) |
| PostgreSQL | Service `postgresql-x64-14` running; `psql` at `C:\Program Files\PostgreSQL\14\bin` | Use it directly; credentials `postgres` / `root` verified |
| Database | `codehub_db` exists and is empty (re-created by owner) | Run migrations into it |
| Workspace folder | `e:\Projects_2026\codehubph` (cannot be renamed to `codehub_ph`) | Use the prompt's alternative: create a `codehub_ph` folder inside the workspace with `manage.py` at its root |

## 1. Folder layout

```
codehubph/                      <- workspace (contains the prompt + this plan)
└── codehub_ph/                 <- project folder (manage.py root)
    ├── venv/                   <- virtual environment (created FIRST)
    ├── .env / .env.example / .gitignore / requirements.txt / README.md
    ├── Dockerfile / docker-compose.yml
    ├── manage.py
    ├── codehub_ph/             <- Django project package
    │   ├── settings.py         <- single settings file, 100% driven by .env
    │   ├── urls.py / wsgi.py / asgi.py
    ├── accounts/  catalog/  capstone/  orders/  payments/  dashboard/  core/
    ├── templates/              <- base.html, partials/, per-app folders, emails/
    ├── static/                 <- css/app.css, js/app.js, js/checkout.js, js/dashboard.js, img/
    ├── media/                  <- PUBLIC uploads (thumbnails, screenshots, GCash QR)
    └── private_media/          <- PRIVATE uploads (product files, capstone source/docs, payment proofs)
```

## 2. Setup steps (section 2 of the prompt, in order)

1. `mkdir codehub_ph`, then `py -V:Astral/CPython3.12.14 -m venv venv` and activate it.
2. Upgrade pip; install `Django 5.x`, `psycopg[binary]`, `python-decouple`, `Pillow`, `whitenoise`, `gunicorn`, `django-axes` (login rate limiting), `requests` (PayPal REST API); `pip freeze > requirements.txt`.
3. `django-admin startproject codehub_ph .` inside the folder, then `python manage.py startapp` for the 7 apps.
4. Create `.env` (values from the prompt + generated `SECRET_KEY`), `.env.example` (placeholders), `.gitignore` (`.env`, `venv/`, `__pycache__/`, `media/`, `*.pyc`, plus `private_media/`, `staticfiles/`).
5. `DATABASES` -> `django.db.backends.postgresql` from `DB_*` env vars.
6. `python manage.py check` and `migrate` after each major step.

## 3. Architecture

- **Server-rendered Django templates** + Bootstrap 5.3 (CDN) + Bootstrap Icons + Inter font + vanilla JS. No DRF/SPA. Small JSON endpoints only for PayPal create/capture and webhooks.
- **Custom user model** (`accounts.User`, extends `AbstractUser`, unique required email, phone, school; no username field). Login by email only. `django-axes` locks out after repeated failures.
- **Private file storage** (`core.storage.PrivateMediaStorage`, a `FileSystemStorage` rooted at `PRIVATE_MEDIA_ROOT` with no `base_url`). Files are only served through permission-checked views using `FileResponse` (never a public URL).
- **Upload validation** (`core.validators`): extension allow-list, configurable max size, Pillow image verification; `upload_to` functions rename every file to `<uuid4>.<ext>`.
- **Site settings** singleton model (`core.SiteSettings`) editable in `/manage/settings/`, defaults from `.env` (`SITE_NAME`, `PAYPAL_ME_URL`, ...), exposed to templates via a context processor.
- **Payable abstraction**: both `orders.Order` and `capstone.CapstoneRequest` implement the same small interface (`reference`, `amount_due`, `currency`, `customer`, `can_be_paid`, `mark_paid()`, `on_payment_submitted()`, `on_payment_rejected()`), so one checkout page and one `Payment` model serve both.
- **Payment providers** (`payments/providers/`): one module per method behind a `PaymentProvider` base class and a registry chosen by settings:
  - `paypal_manual.py` (default): PayPal.me link `https://paypal.me/faintedbrain63/<amount><CURRENCY>` + transaction ID/screenshot -> admin verification.
  - `paypal_checkout.py` (feature flag `PAYPAL_MODE=automated`): Orders API v2 create/capture server-side, sandbox/live switch.
  - `gcash_manual.py`: account name/number/QR + unique reference -> receipt upload -> admin verification. `gcash_paymongo.py` stub shows where an automated gateway plugs in.
  - `card_paypal.py`: PayPal Advanced Card Fields (hosted iframes; server only sees PayPal order IDs). `card_paymongo.py` / `card_stripe.py` adapter stubs.
  - `paypal_api.py`: thin REST client (OAuth token cache, create/capture/get order, webhook signature verification), all calls with `PayPal-Request-Id` idempotency headers.
- **State changes** in `transaction.atomic()` + `select_for_update()`; fulfillment is idempotent (paying an already-paid order is a no-op). Webhook events are stored with a unique event ID so replays are ignored. Money is always `Decimal`.
- **Notifications** (`core.notifications`): plain-text emails from templates (console backend in dev, SMTP in prod) for order received, payment approved/rejected, download ready, capstone status changes.

## 4. Models (ERD in text)

```
accounts.User (AbstractUser)
  email (unique, required), phone_number, school, is_staff -> Admin role, else Customer

core.SiteSettings (singleton, pk=1)
  site_name, tagline, contact_email, contact_phone, paypal_me_url,
  gcash_account_name, gcash_number, gcash_qr (public image), payment_instructions

core.ContactMessage
  name, email, subject, message, created_at, is_resolved

catalog.Product
  name, slug (unique), category [software|web_app|mobile_app], short_description, description,
  features (one per line), price (Decimal), thumbnail (public), file (PRIVATE), file_size,
  version, demo_url, tech_stack (comma tags), status [draft|published], is_featured,
  published_at, created_at, updated_at       idx(status, category), idx(status, -published_at)
catalog.ProductImage   product FK -> Product, image (public), caption, sort_order

orders.Order
  number (unique, e.g. FB-7KX2M9QP), user FK -> User, status [pending|awaiting_verification|paid|rejected|refunded],
  subtotal, total, currency, paid_at, refunded_at, created_at, updated_at       idx(user, status)
orders.OrderItem
  order FK -> Order, product FK -> Product (PROTECT), product_name, unit_price,
  download_count, download_limit, access_expires_at

capstone.CapstoneProject
  title, slug, field [web|mobile|desktop|iot|data_ai|game|other], short_description, description,
  features, tech_stack, suggested_price, thumbnail (public), source_code (PRIVATE, required),
  documentation (PRIVATE, optional), status [draft|published], created_at, updated_at
capstone.CapstoneRequest
  reference (unique, e.g. CAP-4F9K2Q), customer FK -> User, project FK -> CapstoneProject,
  school_name, program, group_members, customization_notes, preferred_deadline,
  agreed_price (nullable until quoted), quote_notes, cancel_reason,
  delivered_source (PRIVATE, optional custom build), delivered_documentation (PRIVATE, optional),
  status [submitted -> quoted -> accepted -> paid -> in_progress -> delivered -> completed | cancelled],
  quoted_at, accepted_at, paid_at, delivered_at, completed_at, cancelled_at, created_at, updated_at
capstone.CapstoneMessage
  request FK -> CapstoneRequest, sender FK -> User, body, created_at

payments.Payment
  order FK -> Order (nullable) XOR capstone_request FK -> CapstoneRequest (nullable)   [check constraint]
  customer FK -> User, amount (Decimal), currency, method [paypal|gcash|card], provider (module code),
  status [pending|awaiting_verification|completed|rejected|refunded|failed],
  provider_reference (PayPal txn/order ID or GCash ref), proof_image (PRIVATE),
  idempotency_key (uuid, unique), raw_response (JSON), admin_notes, rejection_reason,
  verified_by FK -> User, verified_at, created_at, updated_at
  unique(method, provider_reference) where reference != '' and status != rejected
payments.WebhookEvent
  provider, event_id (unique), event_type, payload (JSON), processed_at, created_at
```

## 5. URL map

| URL | Purpose | Access |
|---|---|---|
| `/` | Landing page (hero, featured products, capstone section, how it works, trust, FAQ, contact) | Public |
| `/contact/` (POST) | Contact form | Public |
| `/terms/`, `/privacy/` | Policy pages | Public |
| `/products/` | Catalog: search, category filter, price sort, pagination | Public |
| `/products/<slug>/` | Product detail with gallery + Buy now / Add to cart / Download if owned | Public |
| `/capstone/` | Capstone Services page | Public |
| `/capstone/<slug>/` | Capstone project detail | Public |
| `/capstone/<slug>/request/` | "Request this project" form | Login |
| `/account/register/`, `/account/login/`, `/account/logout/` | Auth | Public |
| `/account/password-reset/...` | Password reset by email (4 steps) | Public |
| `/account/` | Customer dashboard | Login |
| `/account/profile/`, `/account/password/` | Profile, change password | Login |
| `/account/capstone/` , `/account/capstone/<ref>/` | My capstone requests, request detail + messages + downloads | Owner |
| `/account/capstone/<ref>/accept/ · cancel/ · complete/ · message/ · download/<kind>/` | Customer capstone actions | Owner |
| `/cart/`, `/cart/add/<slug>/`, `/cart/remove/<slug>/`, `/cart/checkout/` | Session cart | Login for checkout |
| `/orders/`, `/orders/buy/<slug>/`, `/orders/<number>/`, `/orders/<number>/invoice/` | My orders, Buy now, detail, printable receipt | Owner |
| `/orders/download/<item_id>/` | Secure product download | Owner + paid |
| `/pay/<order|capstone>/<reference>/` | Unified checkout (PayPal / GCash / Card tabs) | Owner |
| `/pay/<order|capstone>/<reference>/submit/<method>/` (POST) | Manual payment proof | Owner |
| `/payments/paypal/create/`, `/payments/paypal/capture/` (POST JSON) | PayPal Orders API v2 (PayPal + card) | Owner |
| `/payments/webhooks/paypal/` (POST) | Signed PayPal webhook | PayPal |
| `/manage/` | Admin dashboard (totals, recent orders, revenue chart) | Staff |
| `/manage/products/...` | Product CRUD + screenshots | Staff |
| `/manage/capstone/projects/...` | Capstone project CRUD | Staff |
| `/manage/capstone/requests/...` | Requests: quote, status changes, deliverables upload, messages | Staff |
| `/manage/orders/...` | Orders: filter, detail, approve/reject payment, refund, resend access | Staff |
| `/manage/payments/...` | Verification queue, approve/reject, proof viewer | Staff |
| `/manage/customers/`, `/manage/settings/` | Customer list, site settings | Staff |
| `/admin/` | Django admin (all models registered) | Superuser/staff |

## 6. Key flows

**Product purchase:** Buy now (or cart checkout) -> `Order(pending)` -> `/pay/order/<number>/` -> choose method.
- PayPal manual / GCash: submit transaction ID + proof -> `Payment(awaiting_verification)`, order `awaiting_verification` -> admin approves (order `paid`, download access granted, email) or rejects with a reason (order `rejected`, customer can pay again).
- PayPal automated / Card: JS SDK -> server creates PayPal order -> customer approves / enters card in hosted fields -> server captures and verifies amount, currency and `custom_id` -> order `paid`. Webhook confirms as a backup.

**Secure download:** `/orders/download/<item_id>/` checks login, ownership, order status `paid`, download limit and access expiry, then streams the private file with a safe filename. Refund revokes access; "Resend access" resets the counter and expiry.

**Capstone service:** Request form -> `submitted` -> admin sets quote -> `quoted` -> customer accepts -> `accepted` -> customer pays via the same checkout -> `paid` -> admin `in_progress` -> uploads deliverables -> `delivered` -> customer/admin `completed`. `cancelled` is possible before payment. Source code and documentation are downloadable only from `paid` onward, by the owner only. Capstone projects never appear in the catalog and cannot go through Buy now/cart.

## 7. Tests (section 8)

- `accounts`: register (unique email), login by email only, logout, profile requires login.
- `catalog`: draft products hidden from list/detail/landing; published visible; capstone items absent from catalog.
- `orders`: cannot download unpaid / someone else's file; paid owner can; limit enforced; refund revokes.
- `payments`: manual submission -> awaiting verification; staff approval -> paid + access; rejection requires reason; non-staff cannot approve; double approval is idempotent; capture amount mismatch is refused.
- `capstone`: full workflow, invalid transitions blocked, non-owner gets 404, downloads blocked before payment.

## 8. Deliverables checklist

- [x] venv + requirements.txt + .env/.env.example/.gitignore
- [x] 7 apps, models, migrations, Django admin registrations
- [x] Templates (base + partials + pages + emails), static CSS/JS
- [x] Payments (providers, checkout, JSON endpoints, webhook)
- [x] Custom admin portal at `/manage/`
- [x] `seed_demo` management command (sample products with generated thumbnails + zip files, capstone project, demo customer, admin)
- [x] Tests passing; `manage.py check` clean
- [x] README (setup, PostgreSQL, migrations, superuser, seeding, payments config, tests, production checklist, PCI notes, defaults chosen)
- [x] Dockerfile + docker-compose.yml
