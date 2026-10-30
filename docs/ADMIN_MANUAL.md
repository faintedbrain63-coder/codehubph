# CodehubPh application manual

This manual describes the current application. It contains no account credentials or customer records. The complete document is supplied as reference context to the admin assistant for each question; it is not model training. The live revenue snapshot supplied separately is the only source of current financial figures.

## 1. Purpose and account roles

CodehubPh offers custom web applications, mobile applications and software development. Clients include students working on capstone projects, local government units, military organizations, businesses and other organizations or individuals. Scope, price and delivery depend on the project brief and accepted quote. The website no longer offers new ready-made software or mobile-app purchases. Historical purchase records and valid customer downloads remain available.

Visitors can browse services, the public portfolio, approved customer comments, contact information and legal documents. Customers sign in to manage their own profile, requests, payments, deliverables, historical purchases and reviews. Staff use the admin workspace at /manage/. Advanced Django administration is at /admin/ and is subject to its model permissions. Customer accounts cannot open the staff workspace or chatbot.

## 2. Registration, sign-in and account settings

Accounts use email and password. Registration requires agreement to the current Privacy Policy and Software License Agreement and Terms of Service. The application records the accepted document versions and acceptance time. A stale registration form must be reloaded to accept the current versions. Registration does not automatically accept later revisions. Current documents are at /privacy/ and /license/, with /terms/ showing the license and terms; dated copies remain available under /legal/.

Staff sign-in opens /manage/. Customers open their own dashboard at /account/. New public registrations must verify their email before signing in. Verification links expire after 24 hours by default; forgot-password links expire after one hour. Both use the configured SMTP service and the `send_auth_emails --loop` delivery worker. Django admin shows delivery status and supports retrying failed jobs. See [account email operations](ACCOUNT_EMAIL.md). A new customer receives an onboarding guide after activation and sign-in and can replay the guide from the account page.

Admins use Settings at /manage/settings/ for Profile, Password, Store and AI connection. Customers use /account/settings/. Profile and password sections save independently. A password change requires the current password and matching valid new passwords. The current device remains signed in. Editing a profile does not grant staff permissions. My purchases remains available for staff who also have a purchase history.

## 3. Public website and service listings

The landing page at / introduces custom development services, the project workflow, published portfolio projects and approved testimonials. Services at /services/ can be searched by title or technology and filtered by field. A service detail page describes a starting price, features and technologies. A starting price is not a final accepted project quote.

Admins manage service offerings under Projects → Project services at /manage/capstone/projects/. Create or edit a service with a title, field, short description, description, starting price, optional features, technologies, thumbnail and reference files. Drafts stay hidden from public listings. Published offerings can be requested by customers. Staff can preview draft records and inspect private uploads. Existing records referenced by requests are preserved rather than destroying customer history.

## 4. Project requests and quotes

Customers can start a project brief at /projects/request/ or request a published service. The brief identifies the client type, project title, platform, school or organization, requirements and optional deadline. Student requests require course/program information. Group members and other optional details can be provided when relevant.

Customers find their own requests at /account/capstone/. Admins use Projects → Project requests at /manage/capstone/requests/. Open the request reference to inspect its brief, messages, payment state, quote and deliverables. Search and filters help locate requests. Use the quote action to enter the agreed price, currency and quote notes, including scope and timeline. The customer accepts the quote and then pays. A submitted brief, a quoted amount and an accepted quote are not revenue until a payment is confirmed.

The normal progression is Submitted → Quoted → Accepted → Paid → In Progress → Delivered → Completed. Before payment, a request can be re-quoted or cancelled through allowed actions. Paid and in-progress work can be delivered. Delivered work can return to In Progress or be completed. Completed and cancelled requests have no ordinary next status. The application enforces allowed transitions; the chatbot cannot override them.

## 5. Payments, verification and refunds

Payments for project requests and historical orders use one checkout system. Amounts and currency are calculated on the server from the agreed quote or order. Customers cannot set an arbitrary amount in the browser.

In manual PayPal mode, customers follow the PayPal.me link, pay the displayed amount, then submit the transaction reference and optional proof. GCash checkout shows the saved number or QR code; the customer pays in GCash and submits the reference/proof. Manual submissions wait for staff verification. Admins open Clients → Payments at /manage/payments/, inspect the payment and proof, and approve only after checking the actual provider receipt. Rejecting requires a reason visible to the customer, who can submit a new attempt. Approval is idempotent and grants the appropriate paid access.

Automated PayPal and card payments are confirmed through the provider's server-side capture/webhook flow. Gateway payments cannot be manually approved as if they were manual payments. Provider availability depends on server configuration. PayMongo and Stripe adapters are placeholders and must not be described as working gateways.

For a refund, return the funds through the actual payment provider and then record the refund on the paid order/request in the admin workspace, or allow the verified gateway webhook to synchronize it. Recording a manual refund in this app does not move money. Refunding revokes the associated paid download access. Full refunds are excluded from the current completed-payment totals. Partial refunds are not tracked as a complete accounting ledger.

## 6. Delivery, files and historical purchases

Admins upload customer-specific source/build and optional documentation using the request's deliverables section. After payment, customers can access the files allowed by the request's state. When customized files are present, those are used for that customer; service reference files can be used as the fallback. Marking a request Delivered records progress; the customer can mark delivered work Completed. Use request messages to discuss delivery and required adjustments.

Private source code, deliverables and payment proofs are served through permission-checked routes, not public storage links. Staff can inspect authorized private files. Customers can download only files they are entitled to. The chatbot cannot open those files, inspect source archives or grant access.

Historical orders appear in Purchase history when records exist. Customers retain their own purchase library, receipts and valid downloads. Downloads have configured expiry and attempt limits. Admins can inspect an order, record a refund or resend/reset access through the available order actions. New ready-made product sales are disabled; historical records are not new service offerings.

## 7. Portfolio introduction and project publishing

Open Our work → Portfolio projects at /manage/portfolio/. Choose Edit introduction & profile to open /manage/portfolio/presentation/. Set the portfolio eyebrow, heading and introduction. Optionally enter a developer or studio name, professional title, biography, expertise, location, GitHub/code repository link and LinkedIn/professional profile link. Leave the profile blank to show projects only. Save the portfolio. The landing-page visibility checkbox controls the landing section; turning it off does not unpublish individual project pages in the public portfolio directory.

Choose Add project to create a portfolio entry. Enter the title, platform (web application, mobile application or desktop/software), completed/ongoing stage, summary and optional description/technologies. Web applications can include a live project or demo URL. Mobile apps and software can be presented with screenshots. Up to twelve screenshots can be added, ordered, captioned or removed in the project editor. URLs must use HTTP or HTTPS. Screenshots are available publicly only when the project is published, apart from authorized staff previews.

Optional Case study details include sector/project context, year, your contribution, challenge, solution and actual result/outcome. Leave unused fields blank; empty case-study headings are not displayed. Do not invent client endorsements or results. Link a customer or project request privately if that customer should review the work.

Save a project as published to make it appear in /portfolio/ and eligible for the landing page. Drafts remain private. Featured projects are sorted first; the first featured published project gets the large landing-page showcase. The landing page shows up to six published projects, with View all projects opening the full directory. The showcase adapts to screen size, light/dark theme and project platform. Deleting a portfolio project also removes its associated project reviews, so review the deletion confirmation.

## 8. Reviews and testimonials

Customers can review projects privately linked to their account through My project reviews at /account/project-reviews/. Project publication and review ownership rules are enforced. Customers with qualifying paid work can also leave their general review from the account. Reviews use a star rating and text, with publication consent where required. A new or edited comment enters moderation before public display.

Admins open Customer comments at /manage/testimonials/ to approve, hide, feature, edit or delete a testimonial. Only approved comments appear on the landing page. Reviews associated with unpublished portfolio projects stay off public testimonial displays. Featuring affects ordering. Staff can add genuine comments received through other channels; do not present invented comments as real customer experiences.

## 9. Support, customers, search and workspace controls

Visitors submit support questions through /contact/. Admins find them in Support inbox at /manage/messages/. Search open, resolved or all messages and mark handled messages resolved. Request-specific messages remain attached to the relevant project request. The chatbot does not send email, reply to clients or resolve inbox items.

Customers at /manage/customers/ shows account information and history links for staff. Global search at /manage/search/ finds matching projects, requests, customers and related records; it limits each result group and links to the full section. List pages support search, allowed filters, pagination and page sizes of 20, 50 or 100 where provided. Search results respect the viewer's permissions.

On smaller screens, use Menu to open the staff navigation drawer. The theme button switches light/dark mode. Required fields and server validation errors remain visible. Editors warn about unsaved changes. Destructive actions require explicit form actions, CSRF protection and, where present, confirmation. The chatbot's text is not a substitute for saving a form.

## 10. Store, privacy, advertising and server configuration

Settings → Store edits the CodehubPh site name, tagline, support contacts, manual PayPal.me destination, GCash account details/QR and payment instructions. These update public branding or checkout instructions. Profile and Password edit the signed-in admin's own account separately. SMTP settings, gateway secrets, legal operator identity/contact settings, upload limits and deployment settings belong in the server environment, not in chatbot messages.

The public website includes the configured Google AdSense loader; the staff workspace excludes it. Including the loader does not guarantee ads, revenue, approval or regional consent compliance. This app does not import AdSense earnings into its payment records, so the assistant's revenue reports do not include advertising income.

Registration links show the currently versioned privacy and license/terms documents. Published document versions must be preserved when updating the legal text. Use the repository's legal-document process and arrange any necessary professional review. The chatbot can explain this app's workflow; it cannot certify legal compliance.

Uploads validate configured size/type rules. Large staff file uploads use chunked transfers where configured. A validation error or interrupted upload must be resolved before saving. File validation does not scan for malware. Demo data and fake preview records are for local testing and must not be presented as real projects, customers or reviews.

## 11. AI provider connection and chatbot

Open Settings → AI connection at /manage/settings/ai/. Select Claude/Anthropic, OpenAI, Kimi/Moonshot, DeepSeek, OpenRouter, GLM/Z.ai or MiniMax. Model is an editable text field: enter the exact API model ID your account supports. A new connection starts with that provider's current verified frontier default. Saved model IDs are preserved. Use frontier default fills the latest verified default into the text field; save to apply it. The endpoint is filled automatically from the provider and model, including GLM-5.3's official coding endpoint. Enter that provider's API key, select Use this connection for the admin chatbot and save. Credentials are saved encrypted on the server. A blank key field keeps that provider's existing key. Switching providers clears the unsaved key field to avoid sending the wrong key to another provider. Only one saved connection is active at a time.

Test saved connection sends a small test request using the saved key/model. Save changes before testing. Test calls and chat questions may use the provider's paid credits. Refresh saved provider models shows model IDs for reference where discovery is supported; it does not replace your typed model or require choosing from a list. Model discovery is unavailable for GLM and MiniMax. A model ID or default does not guarantee account access or compatibility. Defaults were verified on October 24, 2026; they are maintained in the application rather than automatically selecting a new paid model on every visit. Removing a saved key disables the chatbot if that connection was active. You can also disable a connection while retaining its saved key.

Open AI chatbot at /manage/assistant/. Type a question or use a suggested prompt, then Send. Enter sends a message; Shift+Enter adds a line. Every question includes this entire manual, current server-calculated revenue totals and up to the latest six conversational exchanges. History is scoped to the signed-in user's browser session. New chat clears that session's conversation. The manual is available to staff at /manage/manual/ and can be downloaded. Update docs/ADMIN_MANUAL.md when app behavior changes; the assistant reads the deployed file for every question.

The selected external AI provider receives your messages, the manual and revenue aggregates. The built-in context contains no customer names/emails, payment proofs, transaction IDs, source files, account passwords or provider keys. Do not paste sensitive customer information or credentials into questions. The assistant is read-only and has no database-query, code-execution or record-changing tools. Answers may be imperfect; use actual app records and the authoritative revenue cards to verify details.

## 12. Revenue definitions and reporting periods

Ask: How much is my revenue today? What is my revenue this week, this month and this year? Or use Show my revenue. The chatbot and its revenue cards receive freshly calculated totals, not training data or a browser-supplied figure. The cards are rendered from the server's aggregates independently of the model's answer.

Revenue here means retained confirmed receipts: Payment records currently marked Completed, counted by verified_at. Pending, Awaiting Verification, Rejected, Failed and Refunded records are excluded. Created date, quote date, accepted request value, order total without confirmed payment and forecast revenue do not count. Records missing a verification timestamp are excluded. Confirmed custom-development payments and historical product payments are included. Different currencies are reported separately and never converted or added together.

Today starts at local midnight. This week starts Monday at local midnight. This month starts on the first day at local midnight. This year starts January 1 at local midnight. All periods end at the snapshot's current as-of timestamp in the configured application timezone (Asia/Manila by default). A week may begin in the previous month or year. These are calendar-to-date periods, not rolling 7/30/365-day windows. Each answer should include the currency, period start, timezone and as-of time.

A full refund removes that payment from its original verification period's current retained total. These totals are before gateway fees, expenses and tax; they are not profit, recognized accounting revenue, or a refund-date cash-flow ledger. Partial refunds and AdSense earnings are not deducted/imported by this report. A zero total means no qualifying completed receipts for that period. Totals can change after payment verification or refund. Arbitrary past periods, future forecasts, detailed customer breakdowns, expenses, tax and profit are not supplied to the chatbot. Use the payment list for individual records and an appropriate accounting system for a complete ledger.

## 13. Troubleshooting

Chatbot disabled: save an API key, choose a model and enable that connection in Settings → AI connection. Rejected key/access: verify the API key, account access and selected model with the provider, then test again. Quota/rate limit: check the provider's API credits and limits or try later. Timeout/unavailable: retry later; the unsent question remains in the composer. Session expired: reload and sign in. A request limit or busy message means wait for the current request to finish before retrying.

Cannot decrypt key: the server encryption key changed or the stored credential is unreadable. Re-enter the provider key in AI connection settings. Server operators should preserve the encryption key with database backups. Never send keys to the chatbot.

Project missing from landing page: check project publication, landing visibility, ordering and the six-project landing limit; open the full portfolio directory. Testimonial missing: check approval, publication consent and linked-project publication. Revenue seems low: check Completed status, verification timestamp, timezone boundary, currency, refunds and the report's exclusions. A quote or unverified payment is not a confirmed receipt.
