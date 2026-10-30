# Prompt for Claude Code: Digital Marketplace + Capstone Service Platform

You are a senior full-stack engineer. Build a complete, production-ready web application. The project is named **`codehub_ph`** (this is also the name of the Django project package that contains `settings.py`). The public-facing store name is **"FaintedBrain Digital Store"** (use a configurable `SITE_NAME` setting so I can rename it later).

## 1. Purpose

A marketplace where I (the owner/admin) sell:

1. **Digital products**: software, web applications, and mobile applications (downloadable files, with optional demo link and screenshots).
2. **Capstone projects for IT students**: sold as a **SERVICE**, not as a plain download. This is handled in its own separate section with its own flow (see section 6).

## 2. Project Setup (DO THIS FIRST, before writing any application code)

Follow these steps in order, in the current empty project folder:

1. **Create a virtual environment first:** `python -m venv venv`, then activate it (`venv\Scripts\activate` on Windows, `source venv/bin/activate` on macOS/Linux). All packages must be installed inside this venv. Never install globally.
2. Upgrade pip, then install Django, `psycopg[binary]`, `python-decouple` (or `django-environ`), Pillow, WhiteNoise, Gunicorn, and any other dependencies, and save them with `pip freeze > requirements.txt`.
3. Create the Django project **only after** the venv is active and dependencies are installed. The project name is **`codehub_ph`**:
   - Name the project folder `codehub_ph` and create the Django project with `django-admin startproject codehub_ph .` (or inside the `codehub_ph` folder, so that `manage.py` sits at that folder's root).
   - The Django project package (where `settings.py`, `urls.py`, `wsgi.py` and `asgi.py` live) must also be named **`codehub_ph`**, so the settings file is at `codehub_ph/settings.py`.
   - Use `codehub_ph.settings` for `DJANGO_SETTINGS_MODULE` (in `manage.py`, `wsgi.py`, `asgi.py`), `codehub_ph.wsgi:application` for Gunicorn, and `codehub_ph` as the name in the README, Dockerfile and docker-compose.
   - Then create the apps listed in section 5 with `python manage.py startapp <name>`.
4. **Create a `.env` file** in the project root (next to `manage.py`) with these values, and make `settings.py` read **all** configuration from it:

```env
DEBUG=True
SECRET_KEY=<generate a long random key>
ALLOWED_HOSTS=localhost,127.0.0.1

DB_NAME=codehub_db
DB_USER=postgres
DB_PASSWORD=root
DB_HOST=localhost
DB_PORT=5432

PAYPAL_ME_URL=https://paypal.me/faintedbrain63
```

5. Also create a `.env.example` with the same keys but placeholder values (no real secrets), and a `.gitignore` that excludes `.env`, `venv/`, `__pycache__/`, `media/`, and `*.pyc`.
6. Configure Django's `DATABASES` to use `django.db.backends.postgresql` with `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` from `.env`. The PostgreSQL database is **`codehub_db`**, the username is **`postgres`**, and the password is **`root`**.
7. Before running migrations, make sure the database exists. If it does not, create it (e.g. `createdb -U postgres codehub_db` or `CREATE DATABASE codehub_db;` via `psql`), then run `python manage.py migrate`. If PostgreSQL is not reachable, tell me clearly what to fix instead of switching databases.
8. Note: the `root` password and `.env` values are for **local development only**. The README must tell me to use a strong, unique password and a new `SECRET_KEY` in production.

## 3. Tech Stack (strict)

- **Backend:** Python 3.12+, Django 5.x, **Django templates only** (no DRF/React/Vue; small JSON endpoints for payments are fine).
- **Database:** PostgreSQL (use `psycopg[binary]`; configure via environment variables from `.env` with `python-decouple` or `django-environ`).
- **Frontend:** **Bootstrap 5.3** (CDN or local static), **vanilla JavaScript** only (no jQuery, no frameworks), Bootstrap Icons.
- **Other:** Pillow for images, WhiteNoise for static files, Gunicorn for production, `.env` for secrets.

## 4. Design Requirements (enterprise-grade, professional, easy to understand)

- Clean, modern SaaS-style UI: generous whitespace, consistent spacing scale, a restrained color palette (one primary brand color, neutral grays, semantic colors for success/warning/danger), and a single readable font (e.g. Inter via Google Fonts).
- Fully responsive (mobile first), accessible (semantic HTML, ARIA labels, keyboard navigation, WCAG AA contrast, visible focus states).
- Reusable template structure: `base.html`, partials for navbar, footer, messages, pagination, product card, status badges.
- Consistent components: cards with subtle shadows, clear primary/secondary buttons, form validation messages, empty states, loading states on buttons, toast/alert messages via Django messages framework.
- Plain-language microcopy. A first-time visitor should understand what to do within seconds. Use clear labels such as "Buy now", "Download", "Request this project".
- Dark text on light background by default. Optional light/dark toggle in vanilla JS is a nice-to-have.

## 5. Apps and Features

Create these Django apps: `accounts`, `catalog`, `capstone`, `orders`, `payments`, `dashboard` (admin portal), `core` (landing/static pages).

### 5.1 Landing page (public)
- Hero section with headline, subheadline, and two CTAs ("Browse Products", "Capstone Services").
- Featured/latest products grid showing **thumbnail, name, category (Software / Web App / Mobile App), short description, and price** (display in PHP by default; currency configurable).
- Section for Capstone Services (separate from products) with a short explanation of how it works.
- "How it works" 3-step section, trust section (secure payments, instant download), FAQ accordion, contact section, footer.
- Products appear here **automatically** once the admin publishes them. No manual HTML edits.
- Product listing page with search, category filter, price sort, and pagination. Product detail page with gallery, description, features, version, tech stack, demo link, and a Buy button (redirects to login/register if not authenticated).

### 5.2 Authentication
- Register, login, logout, password reset by email, email field required and unique.
- Custom `User` model (extend `AbstractUser`) with phone number, school/university (optional).
- Roles: **Customer** and **Admin** (staff/superuser).

### 5.3 Customer portal (registered users only)
- Dashboard: my purchases, my capstone requests, pending/approved payments.
- Browse products, add to cart or "Buy now" (single-product checkout is fine, cart is a plus).
- Checkout page: order summary + **payment method selection** (PayPal, GCash, Debit/Credit Card).
- My Orders page with status badges (Pending, Awaiting Verification, Paid, Rejected, Refunded).
- **Secure download** for purchased digital products: files are served through an authenticated view that checks ownership and a paid status. Never expose raw media URLs. Optional download limit and expiring links.
- Profile page and change password.
- Invoice/receipt page (printable) per order.

### 5.4 Admin portal (custom, Bootstrap-styled, at `/manage/`; also register models in Django admin)
- Dashboard with totals: revenue, orders, pending payments, new customers, recent orders (simple Bootstrap cards plus a small table; chart optional with vanilla JS canvas).
- **Product management (CRUD):** name, slug, category (Software / Web App / Mobile App), short + full description, price, thumbnail, extra screenshots, **the digital file upload (zip/apk/exe/etc.)**, version, demo URL, tech stack tags, status (Draft/Published), featured flag. Publishing makes it appear automatically on the landing page and customer catalog.
- **Capstone project management (CRUD):** see section 6.
- **Order management:** list, filter by status, view detail, **approve or reject manual payments** (GCash / PayPal.me proof), mark refunded, resend download access.
- Customer list, and a simple site settings page (site name, payment instructions, PayPal link, GCash number/QR, contact email).
- Validate uploads (extension allow-list, max size configurable, unique safe filenames). Store files in a **private** media location (not publicly served).

## 6. Capstone Projects (SEPARATE SERVICE)

Capstone is a **service**, so model and flow it separately from products:

- Models: `CapstoneProject` (title, slug, description, category/field, tech stack, suggested price, **source code upload (required)**, **documentation upload (OPTIONAL)**, thumbnail, status), `CapstoneRequest` (customer, project, school info, requested customizations/notes, preferred deadline, agreed price, status workflow, timestamps), `CapstoneMessage` (simple thread between customer and admin on a request).
- Public page "Capstone Services": list of available capstone projects with description, tech stack, and "starting at" price, plus an explanation of what the service includes (customization, guidance, delivery).
- Customer flow: **Request this project** -> submit form -> admin reviews and sets/confirms a quote -> customer sees quote and pays through the same payment methods -> admin delivers the source code (and documentation if available) through secure download in the customer's request page.
- Status workflow: `Submitted -> Quoted -> Accepted -> Paid -> In Progress -> Delivered -> Completed` (plus `Cancelled`).
- Admin can upload the source code and optionally the documentation at any time; the customer only sees/downloads them once the request is **Paid/Delivered**.
- Capstone items must NOT appear in the normal product catalog and must not be purchasable as a plain download.

## 7. Payments (IMPORTANT: implement this correctly and securely)

Supported methods: **PayPal, GCash, Debit/Credit Card**. Build a `payments` app with a clean `PaymentProvider` abstraction so each method is a separate module, with a `Payment` model linked to `Order`/`CapstoneRequest` (amount, currency, method, status, provider reference, proof image, timestamps, admin notes).

### 7.1 PayPal
- My PayPal.me link: **https://paypal.me/faintedbrain63** (store in site settings and `.env` as `PAYPAL_ME_URL`).
- Implement **two modes** controlled by settings:
  1. **Manual (default, works immediately):** checkout shows the amount, and a "Pay with PayPal" button opens `https://paypal.me/faintedbrain63/<amount><CURRENCY>` in a new tab. The customer then returns and submits their **PayPal transaction ID + optional screenshot**. The order becomes `Awaiting Verification` until I approve it in the admin portal.
  2. **Automated (optional, feature-flagged):** PayPal Checkout using the Orders API v2 (server-side create/capture with `PAYPAL_CLIENT_ID` / `PAYPAL_SECRET`, sandbox/live switch). Verify the capture server-side and mark paid automatically. Document how I switch from sandbox to live.
- Note: a PayPal.me link alone cannot notify the app, which is why manual verification exists.

### 7.2 GCash
- Show my GCash account name, number, and QR image (from site settings, editable by admin) with the exact amount and a unique **order reference** to put in the payment notes.
- Customer uploads a **screenshot of the receipt** and enters the GCash reference number. Status becomes `Awaiting Verification`; I approve/reject in the admin portal. Reject requires a reason that is shown to the customer.
- Structure the code so an automated gateway (e.g. PayMongo or Xendit GCash source + webhook) can be plugged in later without rewriting the checkout.

### 7.3 Debit / Credit Card
- **Never store, log, or process raw card numbers, CVV, or expiry on my server.** Card data must be collected through a PCI-compliant **hosted/tokenized** component of a payment gateway (default implementation: **PayPal Advanced Card Fields**; alternative adapter stubs for PayMongo or Stripe Elements). The customer still enters their card details on the checkout page, but the fields are provided by the gateway's secure iframe/JS SDK, and my server only receives a token/order ID.
- Confirm the payment server-side (and via webhook when available) before marking the order as paid. Implement CSRF protection, idempotency (prevent double charge/double fulfillment), and webhook signature verification.
- Display card brand icons and a "Secured payment" note. Explain the PCI approach in the README.

### 7.4 Payment UX
- One checkout page with payment-method tabs/radio cards (vanilla JS to switch panels), a clear order summary, and clear instructions per method.
- Email notifications (console backend in dev, SMTP in prod): order received, payment approved/rejected, download ready, capstone status changes.

## 8. Security and Quality

- Keep a single `codehub_ph/settings.py` driven entirely by `.env` (do not split it into a settings package), with `DEBUG=False` in production, `ALLOWED_HOSTS`, secure cookies, HSTS, CSRF everywhere, password validators, rate limiting on login (e.g. `django-axes` or simple throttling).
- Private file storage with permission-checked download views. Validate and sanitize all uploads and user input. Use `select_related`/`prefetch_related` and database indexes where appropriate.
- Use Django transactions for order/payment state changes. Use `Decimal` for money.
- Include automated tests for: authentication, product visibility (Draft vs Published), purchase access control (cannot download unpaid files), payment approval flow, capstone workflow and permissions.
- Seed command (`python manage.py seed_demo`) creating sample products, a sample capstone project, a demo customer, and an admin user.

## 9. Deliverables

1. Complete working project with the folder structure, `requirements.txt`, `.env.example`, `manage.py`, migrations, templates, static files (custom CSS/JS), and `README.md`.
2. README must include: local setup, PostgreSQL setup, running migrations, creating a superuser, seeding demo data, configuring PayPal/GCash/card settings, running tests, and a production deployment checklist (Gunicorn + Nginx or a PaaS).
3. Optional `Dockerfile` and `docker-compose.yml` (web + postgres).

## 10. How to Work

- First, briefly outline the architecture, models (ERD in text), and URL map. Then build incrementally: project setup -> accounts -> catalog -> landing page -> orders -> payments -> capstone service -> admin portal -> tests -> README.
- After each major step, run `python manage.py check`, migrations, and tests. Fix errors before moving on.
- Keep code clean, commented where non-obvious, and follow Django best practices and PEP 8.
- Do not use placeholder lorem ipsum in the final UI. Write real, professional copy.
- If something is ambiguous, choose a sensible default, note it in the README, and continue instead of stopping.
