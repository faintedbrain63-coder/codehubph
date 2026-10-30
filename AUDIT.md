# Project audit — 2026-10-23

Follow-up: accounts now use email-only authentication, as requested after this audit. The historical username-related
findings below describe the earlier implementation; the username model field has since been removed.

Reviewed the Django apps, models, services, forms, views, admin registrations, routes, templates, JavaScript, CSS,
deployment files, upload/download handling, and existing tests. Applied fixes locally and expanded regression coverage.
This is an evidence-based audit, not a guarantee that every possible defect has been eliminated.

## Findings and fixes

| Area | Finding | Result |
| --- | --- | --- |
| PayPal capture | The verification code required capture details but did not request a complete API response. | Requests now include `Prefer: return=representation`; response identity and capture data are checked before access is granted. |
| Refund security | An empty capture ID could match a completed manual payment. | Refund events require a capture ID, match only gateway payments, and consult the provider's capture state. |
| Refund ordering | Partial refunds were treated as full refunds; early refunds could be lost or followed by an access grant from a late completion event. | Partial refunds are recorded without revoking access. Full refunds are recorded even before completion, and late completion cannot resurrect them. |
| Payment retries | Starting another checkout failed the previous attempt, potentially losing a legitimate in-flight capture. | Matching pending attempts retain their payment ID, provider order and idempotency key. |
| Payment state | Stale/refunded/changed orders could reach capture, and staff could approve unconfirmed gateway payments. | Current payable state and amount are checked before capture. Staff approval/rejection applies to manual verification; gateway outcomes come from the provider. |
| Payment input | JSON arrays/scalars, malformed gateway data, and invalid decimal amounts could cause server errors. | Input shape, identifiers and amounts produce controlled errors. Unknown payment events remain unprocessed for provider retries. |
| Concurrency | Parent/payment locks were acquired in different orders; joined download reads could use stale counters after waiting. | Payment operations lock parent then payment. Downloads acquire the parent lock before re-reading quota and opening the file. |
| Order reuse | A filtered item count could reuse a larger cart order for Buy Now. Cart orders were not reused, and changed prices could retain stale totals. | Reuse compares complete product/price sets in the current currency, with customer checkout serialization. |
| Catalog changes | Products could disappear between selection and checkout. | Re-read published products; refuse changed selections with a recoverable cart/catalog message. |
| Downloads | Missing files and HEAD requests consumed quota. Expired purchases still offered Download on product pages. | Open files before incrementing, do not count HEAD, and show the blocked-access reason and support action. |
| Capstone workflow | An accepted quote could change or be cancelled while payment was under review. The documented staff refund action was missing. | Freeze quote/cancellation during review and add a staff-only action to record an already-issued refund and revoke access. |
| Admin integrity | Direct Django admin edits bypassed payment/workflow services. | Transaction records are view-only there; `/manage/` provides validated actions. |
| Authentication | Case/email aliases split lockout counters. Valid usernames containing `@` could not sign in. | Resolve aliases to a shared lockout identity and support `@` usernames. Add a database constraint for case-insensitive username uniqueness. |
| Database integrity | One gateway capture could be recorded against multiple payments. | Add a unique constraint for nonempty capture IDs. |
| Forms and email | Empty POST data could leave forms unbound; long names could break review submission; email rendering errors escaped error handling. | Bind POSTs consistently, limit stored review names, preserve registration destinations, and isolate email rendering/send failures. |
| Reviews | Linking any user to an admin-entered review implied a verified purchase. | Verified status requires purchase eligibility. |
| Pagination | Elided page links always centered on page 1, and grouped staff queries had no stable ordering. | Generate links around the actual page and enforce ordering. Paginate customer capstone requests. |
| Payment destinations | Process-local settings caching could show an obsolete receiving account in another worker after edits. | Read the singleton settings from the database instead of relying on a process-local cache. |
| Browser resilience | Blocked local storage, a failed Bootstrap load, or unavailable clipboard access could break behavior. | Guard optional browser APIs, keep messages visible, provide copy fallback, and prevent repeated busy-form submissions. |
| Checkout feedback | SDK failure left blank fields; disabled methods remained selectable; absent JavaScript prevented switching manual methods. | Disable unavailable options, select an available default, explain SDK failures, and provide manual-method links without JavaScript. |

The PayPal response fix follows the provider's documented default of a minimal capture response and its
[`return=representation` option](https://developer.paypal.com/api/orders/v2/orders-capture).
The webhook retry behavior follows [PayPal's delivery/retry documentation](https://developer.paypal.com/api/rest/webhooks/rest/).
State changes use [Django transaction and after-commit semantics](https://docs.djangoproject.com/en/5.2/topics/db/transactions/).

## Feature and design critique

The existing shared Bootstrap design, account navigation, private-download model and separate capstone workflow are
useful foundations. A wholesale visual redesign would obscure the more important problems: unclear availability,
misleading actions, and status handling that did not consistently match what customers could actually do.

Changes made from that critique:

- Payment labels and the advertised payment-method count now reflect configured providers. Unavailable checkout
  options cannot be selected, and an empty configuration points customers to support.
- Capstone checkout uses request/accepted-quote wording rather than an unrelated cart breadcrumb.
- Expired or exhausted downloads show a reason and an access-renewal path.
- The feature checkbox now affects the catalog's default ordering; explicit price/name sorting stays meaningful.
- Pagination and request counts reflect the complete result set, and staff list ordering is stable.
- Hidden payment panels remain hidden even when component display rules apply. Long content wraps within cards,
  messages, breadcrumbs and detail fields.
- Dashboard charts redraw with the selected theme; payment errors remain visible and describe uncertainty about a
  charge instead of incorrectly promising that no charge occurred.
- Electronic order summaries use neutral invoice/payment-receipt wording and retain refunded payment references.

These layout changes were checked through source review and rendered templates. They have not been visually
verified at mobile/desktop viewport sizes because the browser tool reported no available browsers.

## Verification

- Original baseline: 77 Django tests passed against PostgreSQL.
- Expanded normal-password-hasher run: 124 Django tests passed.
- Final suite: all 127 Django tests passed, including real multi-connection concurrency tests; final repeat uses Django's fast
  test-only password hasher and treats unordered-pagination warnings as errors. No production password settings changed.
- Four Node.js frontend behavior tests cover storage failure, missing Bootstrap, clipboard fallback and duplicate submits.
- JavaScript syntax checks cover all four application scripts.
- `pip check`: no broken requirements.
- Django system checks and migration consistency checks pass. Production-mode `check --deploy` passes.
- Production-mode static collection succeeds, including compressed/hashed assets. The three CDN integrity hashes
  in `base.html` were independently matched against their downloaded assets.
- Production-mode requests returned HTTP 200 for six public pages and five generated CSS/JavaScript asset URLs.
- Broad response/template checks cover public, customer and staff pages, including detail/edit routes and a Django
  admin record page.

Local additive migrations were applied after confirming a local database and no conflicting username/capture values:
`accounts.0002_unique_username_ci`, `catalog.0002_featured_catalog_help`, and `payments.0002_unique_gateway_capture`.
Deployments must run their own migrations and production static collection before restarting application workers.

## Remaining verification boundaries

- Live PayPal/card/GCash transactions and actual SMTP delivery were not exercised. Payment provider calls are mocked
  in tests; merchant eligibility, credentials, webhook delivery and money movement require sandbox/live integration testing.
- Browser visual inspection was unavailable. The computer-use tool returned no available browser surfaces.
- The local `.env` enables development mode. Running deployment checks against that mode reports the expected
  debug/HTTPS-cookie/HSTS warnings; overriding `DEBUG=False` for the production-mode check clears them.
- PayMongo/Stripe adapters remain explicitly unavailable stubs. They require a separate gateway integration and credentials.
- Existing sample catalog/review content and demo-account guidance remain documented in README; this audit did not
  publish a site, alter production data or issue refunds.
- This directory has no Git metadata, so a Git diff/commit was unavailable. The changes are saved in the workspace.

## Reproduce checks

```powershell
.\venv\Scripts\python.exe -E manage.py test --noinput
node --test tests/frontend.test.cjs
.\venv\Scripts\python.exe -E manage.py check
.\venv\Scripts\python.exe -E manage.py makemigrations --check --dry-run
.\venv\Scripts\python.exe -E -m pip check
```

Load production environment values before `check --deploy` and `collectstatic`. Keep private media outside all public
web-server routes, as described in README.

## Email-only account follow-up

Removed the separate username model field, registration/profile controls, admin user fields, search filters and email
template references. Email is the unique login identifier for customers and administrators; Django's built-in admin
login retains its internal credential field name while accepting email only. Lockouts normalize email case and spaces.
The account manager and `createsuperuser` command accept email without a username. Public reviews use a name or
"Customer" rather than exposing an email as a fallback name.

Migration `accounts.0003_email_only_login` validates and normalizes existing emails before dropping the username
constraint/column. The local migration preserved both existing account IDs, password hashes, permissions and the
existing order. Historical username values are removed; restoring them requires an earlier database backup.

The expanded 140-test Django suite passed, including a migration test that verifies password/permission/foreign-key
preservation and physical removal of the old column. Authentication tests also cover registration, admin account
creation, email changes, password reset, case-insensitive lockouts and rejection of legacy handle-based sign-in.
All 25 account and account-migration tests also passed using the normal production password hasher.

## Registration agreement follow-up

Added detailed Privacy Policy and Software License Agreement/Terms documents with dated versions and public archive
routes. Registration requires two affirmative checkboxes and matching current document versions; the account stores
the server's acceptance timestamp and version identifiers. These records are read-only in Django admin, and legacy
accounts retain empty acceptance values. Missing/false checkboxes, tampered versions, stale forms and invalid account
data cannot create a registered account.

The terms protect the operator's/programmers' intellectual property, limit licensed deployments and redistribution,
define service scope and third-party dependencies, and address lawful refunds, warranty exclusions, liability,
indemnity and termination. Mandatory privacy/consumer rights and express existing promises remain preserved.
Legal owner, address and privacy contact are configurable. Actual owner details and Philippine legal review are still
needed before public use; technical acceptance checks do not establish legal enforceability or full compliance.

The expanded 153-test Django suite passed, plus all 13 new legal-document/registration tests using the normal password
hasher. The new migration is `accounts.0004_registration_legal_acceptance` and does not backfill consent.

## Admin catalog, sidebar and SweetAlert follow-up

Expanded the existing staff console instead of duplicating its payment/access-control workflows. Sidebar links now
separate software, mobile apps and web apps, with a scrollable mobile drawer and upload shortcut. Django admin has
the same management shortcuts in its sidebar (including on its index), a mobile layout and a Store console link.
Replaced the unverified "Store is live" indicators with a truthful staff-workspace label.

Product and capstone management now provide searchable/filterable, paginated lists, staff detail previews (including
drafts), uploads, edits and protected deletion. Product search covers names/slugs/descriptions/technologies; capstone
search also combines field/status filters. Valid product-type links preselect the creation form. Upload inputs show
configured format/size limits while retaining server-side validation and private storage. Gallery and main-form errors
are validated together. Staff-only source/documentation downloads use an explicit file whitelist, attachment headers
and private/no-store responses, without changing customer download allowances. Referenced listings are archived as
Draft instead of deleting order/request history. Capstones remain separately quoted services.

Bundled SweetAlert2 11.26.25 and its MIT license locally. Shared alerts cover Django messages, server/client form errors,
checkout errors and action confirmations in both admin areas and the storefront. Untrusted content is rendered as text;
dialogs are queued, cancellation cannot submit, repeated confirmation clicks are guarded, and acceptance re-submits via
requestSubmit with the original submitter. Ordinary browser validation, CSRF and uploaded form data remain intact.
Errors/warnings stay open until dismissed. Inline messages and native confirmation are library-unavailable fallbacks.

Verification: all 171 Django tests passed (test-only fast password hasher), including 18 new catalog/admin regressions.
Those 18 tests also passed with the normal password hasher. All 15 Node frontend behavior tests passed (11 new alert
tests), along with JavaScript syntax checks, Django system checks, dependency checks and migration-drift checks.
Production-mode deployment checks reported no issues and hashed static collection succeeded. No new schema migration
was needed. Browser visual QA could not complete: no browser-control surfaces were available and the native Chrome
Computer Use approval timed out. Automated rendered-page assertions are not a substitute for desktop/mobile visual QA.

## Admin login landing-page correction

The local `admin@example.com` account already had active/staff/superuser permissions. The missing sidebar after a
standard sign-in was a routing problem: the default login destination was the customer `/account/` dashboard,
which intentionally uses the customer layout. Staff now default to `/manage/`; existing `/account/` bookmarks and
login next-links to that dashboard redirect staff to the same console. Safe explicit destinations are still respected,
external next URLs remain rejected, and staff routing is based on permissions rather than the email address.

Added a prominent Admin console navigation link, a labelled mobile Menu button, and a separate `/account/purchases/`
personal dashboard so staff can still shop without a redirect loop. Customer login behavior is unchanged. The expanded
181-test Django suite and 15 frontend behavior tests passed, including 10 new login/workspace regressions. A read-only
production-mode check with the existing local admin account verified the default redirect, account-bookmark redirect
and rendered staff sidebar. No account flags, passwords, schema or production deployment were changed.

## Workspace redesign and full-width/readability follow-up

Review findings: the staff interface reused storefront navigation, competed with duplicate actions, used overly small
text, and did not consistently distinguish search/filter state from an empty account. Operational work queues were
hard to discover. Several long editors lacked persistent save actions, additional screenshot slots and unsaved-change
protection. Payment/support lists lacked useful search. The customer overview loaded purchase history without a bound,
and capstone discovery/history lacked search. External UI-CDN failures could also leave core layout/controls unavailable.

Implemented a dedicated staff shell with grouped/current-section navigation, a responsive keyboard-accessible drawer,
real review counters, contextual back links, global staff search and a consistent light/dark visual system. Overview
cards lead into the operational queues; bounded 7/14/30-day payment activity includes an accessible exact-value table
and an explicit explanation that partial refunds are not deducted. No invented trends, sales or availability indicators
were introduced. Global search is staff-only, includes drafts and caps each section at five results.

Products, capstone offerings, orders, payments, customers, comments and support share labelled filtering/result patterns.
Page sizes are restricted to 20/50/100. Payment search combines method/status with customer/order/transaction references.
Support defaults to open conversations, offers searchable resolved/all views and retains safe filter return destinations
after resolution; nonexistent messages return 404 rather than a false success. Invalid staff replies now show feedback.
Product/capstone editors have sticky save bars, Save & continue, error summaries, file-selection feedback and up to 12
gallery entries. Client-side edit guards preserve errors/edits on cancelled navigation and do not bypass normal submission,
server validation, private storage, CSRF, payment state transitions or protected deletion.

Customer accounts now use a searchable 12-item purchase library, with stable query counts as history grows. Orders and
project requests have owner-scoped combined search/status filtering, and public capstone discovery searches title/topic/
technology. Search failures offer reset guidance without falsely claiming a customer has no purchases. Existing legal
agreement versions/content, payment verification, download limits and purchase ownership requirements remain unchanged.

At the user's explicit request, all outer page containers use the available screen width with responsive edge padding,
including ultrawide staff content, authentication, legal documents, invoices and advanced Django admin. Storefront body
text is 18px; staff body text 17px and staff tables 16px. Navigation, labels, controls, helper text and previously tiny
landing-page metadata were enlarged. Responsive table positioning prevents visually hidden table headings from widening
phone viewports. The shared final layout/typography rules are in `static/css/layout.css`.

Bootstrap 5.3.3, Bootstrap Icons 1.11.3 (fonts included) and their MIT licenses/source maps are now bundled locally;
downloaded UI CSS/JS matched the previously pinned SHA-384 values. SweetAlert2 remains locally bundled. Google Fonts
are optional with system fallbacks; hosted payment-provider resources still require network access.

Verification: 201 Django tests passed with the test-only fast password hasher, plus 29 Node behavior tests covering
alerts, drawer focus/inert state, file feedback, gallery limits and edit protection. Twenty new server tests cover the
workspace/discovery workflows and owner scoping. Production-mode deployment checks, hashed static-file collection,
dependency consistency and migration-drift checks passed. No new database migration is required.
All twenty new server tests also passed with the normal password hasher (no test hasher override).

The normal desktop Computer Use check could not safely identify the browser URL. Visual QA instead used isolated fake
snapshots generated in a disposable test database and a separate headless Chrome profile, never the user's browser or
production session. Twenty rendering cases passed at 390px, 1440px, 1920px and 2560px, including an open mobile drawer,
dark mode, forms, tables, storefront/catalog, registration, account, checkout, legal pages and invoice. Assertions check
exact viewport sizes, no page-level overflow/clipped catalog content, full-width containers, readable type and no browser
JavaScript exceptions. Screenshots/results are in ignored `.qa/`; repeat instructions are in README.

Limits: these UI/workflow improvements are not an enterprise-security or compliance certification. SSO/MFA, granular staff
roles, a comprehensive append-only staff audit trail, malware scanning, backup/restore drills and production monitoring
remain separate infrastructure/security work. Real gateway capture/webhooks still need merchant sandbox/live integration
testing. Changes are local; no production deployment, permission changes, real payments/refunds or customer-data edits
were performed.

## Independent feature/design review follow-up

A fresh pass over models, payment services, customer flows, landing/catalog templates and rendered pages (headless
Chrome with exact 390px and 1440px device metrics). Earlier decisions stay as they were: no product listings on the
landing page, full-width containers, larger text, email-only login.

| Area | Finding | Result |
| --- | --- | --- |
| Demo seeding | `seed_demo` reset the password of **every** account (real customers and staff included) to a password published in README, and ran with `DEBUG=False`. | Only the two demo accounts get the demo password. Resetting all accounts needs the explicit `--reset-all-passwords` flag. The command refuses to run when `DEBUG=False`. |
| Double charging | A stale pending order (e.g. cart A+B) stayed payable after the customer bought A in another order, so paying it charged for A twice. | Orders have a `payment_block_reason`. Checkout, manual submission, gateway start/capture and staff approval refuse payment for already-owned items, and the customer is offered "cancel and move the other items to the cart". |
| Abandoned orders | Customers could not cancel unpaid orders. They stayed in "open orders" with a Pay button indefinitely. | New `Cancelled` order status (`orders.0002_order_cancellation`, additive) with a customer cancel action for pending/rejected orders. Cancellation is refused while a payment is under review, retires pending gateway attempts, and is never reused for new checkouts. |
| Contact spam | Each public contact submission emailed the owner, with no throttle beyond a hidden honeypot. | Valid submissions are capped at 5 per client IP per hour (HTTP 429 after that). IPs are resolved the same way as the login lockout. The default cache is per process, so use a shared cache to make the cap global. |
| Truthful storefront | The hero, trust panel, FAQ, product page, cart and login page promised GCash, card security and "instant access" even when those methods were not configured. The stats bar showed "1 ways to pay" and a "New" rating tile. | These claims now follow the configured providers. Stats are pluralized, and tiles without information are hidden. The bar resizes to however many tiles render. |
| Thumbnails | `<img height="400">` overrode `aspect-ratio: 16/10`, which forced card images to ~436×400 and cropped both sides (product names were cut off). The product/capstone detail gallery had the same issue. | `height: auto` lets the aspect ratio apply (now 436×272). The width/height attributes stay to prevent layout shift. |
| Mobile header | At 390px the brand subtitle wrapped and the menu button dropped to a second row, giving a ~135px header on every page. | The header now fits on a single row. The decorative subtitle is hidden on phones. |
| Catalog filters | The category dropdown duplicated the category tabs. Tabs dropped the chosen sort. Search ignored the full description and features. | Tabs are the single category control, and the search form keeps the current category. Sort applies when changed, and tabs keep a non-default sort. Search also covers the description and features. |

Verification: new tests in `orders/test_lifecycle.py` and `core/test_storefront_review.py` cover the items above.
Run `migrate` (for `orders.0002_order_cancellation`) and `collectstatic` before deploying.

## Chunked uploads for Nginx + Gunicorn + Cloudflare Tunnel

Cloudflare rejects request bodies over 100 MB, while product/capstone files may be 500 MB. Staff file fields
(product file, capstone source/documentation, request deliverables) now upload in `UPLOAD_CHUNK_MB` pieces to
`/manage/uploads/` (staff-only, CSRF-protected, per-user, resumable through `Content-Range`, with a cap on
unfinished uploads). The form submits a token instead. The finished file passes the field's validators and is moved
into private storage. Partial files expire (`cleanup_uploads`). New migration: `core.0003_chunked_upload`.

Deployment finding: without `django-ipware`, login lockouts and the contact limit used `REMOTE_ADDR`, which behind
Nginx is `127.0.0.1` for everyone. One attacker could lock any account for every visitor. With `BEHIND_PROXY=True`
the app reads Nginx's `X-Real-IP` (resolved from `CF-Connecting-IP`). README documents the Nginx/cloudflared
configuration, including passing `X-Forwarded-Proto` through to avoid an HTTPS redirect loop.

Verification: 242 Django tests (15 chunked-upload, 5 client-IP) and 29 frontend tests pass. A headless-Chrome run
of the real product form uploaded a 5 MB file in six 1 MB chunks, and the stored file's SHA-256 matched the original.

## Width review follow-up

The previous full-width pass removed every width limit, not just the outer containers. At 1920px this produced
~1,700px legal paragraphs (~200 characters per line), sign-in fields ~780px wide inside a 1,830px auth panel, a
password form and a receipt stretched edge to edge, and 590px product cards with very tall thumbnails. On 2560px+
screens the navbar brand and account actions ended up at opposite edges of the screen.

Fix (`static/css/layout.css`): containers stay fluid but stop at `--page-max: 1920px`, so screens up to 1920px look the
same as before and ultrawide screens get centred content with full-bleed section backgrounds. Readable measures are
restored: page-header and landing section text, the auth shell (72rem) and card (34rem), legal prose (~75 characters),
`.form-measure` (password change), `.document-measure` (receipt) and the staff heading and empty-state text. Storefront
card grids use 4 columns from 1700px. The staff workspace content still uses the full width next to its sidebar, since
tables and metrics benefit from it. `tests/browser-render.cjs` now checks the 1920px cap, adds a 2560px storefront case,
and asserts that auth, legal and receipt widths stay bounded.

## Signed-out checkout, first-login tutorial and web apps moved to capstone

- Signed-out visitors who choose Buy now, cart checkout or "Request this project" are sent to registration with a
  sign-in alternative. The purchase resumes after registration or sign-in (order created, payment page opened, or the
  capstone request form shown). Pending purchases are session-only, expire after one hour, and are ignored if the
  product was unpublished in the meantime. Previously Buy now linked to sign-in and dropped the purchase.
- New customers get a 4-step buying tutorial modal, recorded per account (`accounts.0005_onboarding`). The migration
  marks staff and accounts that have signed in before as already onboarded. The tutorial can be replayed from the
  account overview, and the no-JavaScript form fallback redirects only to same-site pages.
- The Web App product category was removed. `catalog.0003_move_web_apps_to_capstone` copies each existing web app
  product into a **draft** capstone offering (field "Web App / System", same text, price, thumbnail and source file) and
  unpublishes the product, re-categorised as Software, so past orders, receipts and downloads keep working. Staff should
  review and publish the new drafts under Capstone projects. Demo seed web apps are now capstone projects.

Verification: 13 new server tests (`accounts/test_purchase_onboarding.py`) and 4 Node tests (`tests/onboarding.test.cjs`).
Run `migrate` and `collectstatic` before deploying.

