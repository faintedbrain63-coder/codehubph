# Responsiveness audit

The project uses a useful Bootstrap foundation, but fixed minimum sizes, non-wrapping text and oversized gutters caused clipping that the global horizontal-overflow rule sometimes concealed. Short landscape screens also exposed controls that fit horizontally but were inaccessible vertically. The fixes address those layouts while retaining the existing features.

## Findings addressed

- Signed-in navigation overflowed at 1440px (document width 1483px). Expanded navigation now wraps and account labels have a bounded width. Recheck: document width 1440px.
- Staff buttons prevented wrapping; narrow page actions now wrap without changing actions.
- Fixed minimum tracks in visitor and storage charts competed for space on phones. Phone layouts now give the visitor bar its own row and allow legend labels to shrink/wrap.
- Flex/grid content, form controls, modal text and footer legal links now accommodate narrow containers.
- Assistant toolbar actions can wrap on phones.
- Footer/contact email links and long project-type badges wrapped poorly or extended beyond narrow columns. They now wrap within their containers.
- Staff heading/action groups could widen the page at intermediate widths. They can now shrink and move onto additional rows.
- Bootstrap's largest row gutters exceeded the page padding near laptop widths. Container padding now accommodates those gutters.
- Tablet admin user forms clipped read-only password summaries and permission selectors. Fields and selector columns now shrink, and labels stack where space is limited.
- Onboarding extended below short screens. Its body now scrolls while header/footer controls stay visible.
- The upload dialog clipped cancellation controls in landscape. Short-screen progress content now scrolls with sticky action controls.
- The screenshot counter split across lines on narrow phones. It now stays together, leaving the project title room to wrap.
- Long unbroken project titles widened staff detail pages or were clipped in customer headers. Headings now wrap safely.
- Staff navigation collapsed to zero height behind its fixed header/footer on short landscape screens. The entire drawer now scrolls in that layout.
- The public navigation/account dropdown could exceed the screen height. Its expanded content now scrolls within the available viewport; the account and sign-out controls remain reachable.

Production changes are CSS and the onboarding dialog's scrollable class only. Features, routes, business logic and existing `.env` edits were left untouched. Optional test fixtures and browser checks were expanded to verify the layouts.

## Evidence

- Django system check passes.
- All 37 existing frontend behavior tests pass.
- Existing workspace preview-generation test passes with process-only `DEBUG=True`, `SECURE_SSL_REDIRECT=False`, `CODEHUB_RENDER_PREVIEW=1`.
- Existing `tests/browser-render.cjs` default matrix passes all 27 cases using isolated Chrome: phone (390px), desktop (1440/1920px), ultrawide (2560px), mobile menu, dark workspace, storefront, forms, settings, checkout, invoice and onboarding. Results and screenshots: ignored `.qa/` directory.
- Visually inspected `.qa/overview-mobile.png`.
- Expanded preview generation covers 80 pages: storefront, catalog/services, portfolio/gallery, account security, customer requests/orders/reviews, staff detail/edit/list pages, manual payment forms, concept-document reader, validation/errors, email and Django admin.
- A 616-case pass over 77 pages at 320/360/576/768/992/1200/1440/2560px completed without clipping reports or browser exceptions. Three further page types were subsequently added.
- Twenty-four detail/payment/representative-page checks passed at 320/768/992/1440px.
- Sixty open-control checks passed at 320×568, 768×1024, 992×740, 1440×900 and 740×360: legal dialogs, multi-image lightbox, onboarding first/last steps, public navigation/account dropdown, staff drawer, confirmation, upload progress/cancellation/error. The upload requests were held or rejected locally; no files or payments were sent.
- Twenty-four stress checks passed with long unbroken project titles, long email addresses and large amounts after correcting heading wrapping.
- Six portfolio/onboarding server tests pass; all 37 frontend behavior tests still pass.
- Reviewed screenshots of the mobile workspace, narrow checkout, tablet admin user form, phone lightbox, and short-landscape onboarding/upload/cancellation dialogs.

## Final verification

Final checks completed successfully:

- All 640 cases across 80 pages and eight widths pass, including checks for text overflowing inside headings/buttons. No browser exceptions. Results: `.qa/matrix-results.json`; log: `/tmp/codehub-final-matrix.log`.
- All 32 shared-layout cases pass at 280/575/767/991/1199/1280/1920/3840px. Results: `.qa/boundaries-results.json`.
- All 60 final open-control cases pass, including viewport bounds, scrollable content, accessible overlay buttons, nonzero staff navigation height and bounded public navigation. Results: `.qa/controls-results.json`.
- All 24 long-content stress cases pass. Results: `.qa/stress-results.json`.
- All 24 additional detail/payment screenshot cases pass. Results: `.qa/details-results.json`.
- Final frontend run: 37 tests passed. Django system check and `git diff --check` pass.
- Final screenshot review confirms the short-screen upload/cancellation controls, staff drawer links and account/sign-out menu are visible/reachable.
- Worktree review confirms production edits are confined to responsive CSS and the onboarding dialog class. Existing environment edits remain untouched.

## Reproduction and limits

Generate the existing previews using the `CODEHUB_RENDER_PREVIEW`, `CODEHUB_RENDER_PORTFOLIO`, `CODEHUB_RENDER_ACCOUNTS`, `CODEHUB_RENDER_SERVICES`, and `CODEHUB_RENDER_AI` flags on their respective optional preview tests. Use `DEBUG=True SECURE_SSL_REDIRECT=False` for these local test processes; do not change production configuration. The workspace preview test also exports admin static assets and translation JavaScript.

Serve `.qa/site` on localhost port 8766. Set `CHROME_BINARY` to the installed Chrome executable, then run `CODEHUB_RENDER_MATRIX=1 node tests/browser-render.cjs` for all previews, or `CODEHUB_RENDER_CONTROLS=1` for open controls. Optional settings: `CODEHUB_RENDER_FILTER` (filename regex), `CODEHUB_RENDER_WIDTHS` (comma-separated widths), `CODEHUB_RENDER_STRESS=1`, `CODEHUB_RENDER_SHOTS=1`, and `CODEHUB_RENDER_NAME` (separate report/profile name).

The audit uses real browser rendering with offline font fallbacks, fake test records and a separate browser profile. Horizontal scrolling remains available in data tables and intentional rails. Decorative layers are distinguished from actionable content. Live third-party payment iframe rendering and physical-device testing are outside these local checks; no provider transactions were made.

The local fake-page server uses port 8766 and `.qa/site`. Preview generation requires local PostgreSQL access. No production data or browser sessions are used.
