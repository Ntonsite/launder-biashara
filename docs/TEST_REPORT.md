# Test report — Phase 1

Run on 2026-10-08, Windows 11, Python 3.12, Node 22, Flutter 3.41.6 / Dart 3.11, Docker 29.
Updated the same day for the provider workspace and walk-in pass (API and web rows below re-run; mobile unchanged).
Everything below was actually executed; nothing is extrapolated.

## Summary

| Suite | Result |
|---|---|
| API — pytest (fresh `launder_test` database on the PostGIS container, migrations 0001–0004 + seed) | **67 passed** |
| API — ruff | clean |
| API on PostgreSQL 16 + PostGIS 3.4 (Docker) | migrations to `0003` applied over existing data (backfill checked: every order has a promised time, every paid payment a `paid_at`); `ST_DWithin` uses `ix_businesses_geog`; overdue/pipeline counts use `ix_orders_business_status`; Redis rate limiting active |
| Web — TypeScript (`tsc -b`) | clean |
| Web — Vitest | **15 passed** |
| Web — production build | OK (main bundle 119 KB gzip; business/admin lazy-loaded) |
| Web — Playwright E2E, Chromium, against Docker API | **13 passed** (customer journey, Swahili, admin review, walk-in counter, dashboard click-through + reports, staff role, phone dashboard, finance admin monetization, read-only admin, free laundry → Pro trial, pilot laundry on desktop and phone); provider tests also passed with `--repeat-each=2` |
| Web — Docker image (nginx) | builds; serves app, proxies `/api` and `/media`, SPA deep links |
| Mobile — `flutter analyze` | no issues |
| Mobile — `flutter test` (unit, repository, widget, layout) | **35 passed** |
| Mobile — on-device acceptance (Android 13 phone, real API on PostGIS) | **passed** |
| Mobile — Android release APK (`--release`, minified) | built (61 MB universal APK) |
| Mobile — iOS build | **not run** (requires macOS/Xcode) |

## API (`apps/api/tests`)

* `test_auth.py` (14) — health/readiness, staff login and token pair, error envelope with request id, login
  lockout, refresh rotation and reuse detection, logout revocation, customer OTP sign-up, local phone formats,
  invalid phone, resend cooldown, attempt counting and lock, customer blocked from business/admin, expired
  token message, refresh token rejected as access token.
* `test_marketplace.py` (12) — distance sort (FreshWash closest to Mikocheni), radius, pending business never
  public, pickup/service/search/rating filters, no-location browsing by rating, storefront grouping and
  distance, server-side quote, quantity rules, pickup slots inside hours, open-now logic, areas.
* `test_orders.py` (11) — **full marketplace journey** (5 shirts + 2 trousers, pickup, TZS 18,000,
  idempotent replay, business sees same order, invalid jump refused, full status walk, payment required to
  complete, cash recorded, customer sees identical event history, confirm, 5 % commission on services,
  review updates rating, notifications recorded, reorder at new price with change list, stale total refused),
  ownership isolation (customer and business), cancel rules, rejection reason, drop-off stages, pickup
  validation (radius, slot, no pickup), idempotency key and name required, mobile-money sandbox with signed
  webhook and duplicate callback, failed payment retry, counter order pricing, state machine unit rules.
* `test_business_admin.py` (7) — register → not listed → readiness checklist → apply → admin detail →
  approve → public → decision rules → suspend → hidden; audit actor; RBAC server-side; staff permissions;
  owner adds staff; dashboard uses real commission; review moderation recomputes rating; revenue excludes
  unpaid.

## Provider workspace and walk-in (API)

* `test_business_ops.py` (13) — period maths (month-to-date vs same days of a shorter month, finished months,
  same weekday last week, Monday weeks, custom validation); setup checklist instead of zeros; dashboard keeps
  sales, collections and outstanding apart (an old order paid today is collected today, not sold today);
  promised time from the slowest service; discounts; day book (opening, new, carried forward); overdue and
  due-today drive attention items, order views, counts and sorting; ready-late lowers on-time rate; comparisons
  only with ≥ 5 orders; roles (cashier takes orders and money but cannot wash, staff cannot create orders, see
  money, customers or reports, manager gets daily but not monthly, driver sees only pickups); CRM spend,
  segments, preferred services, add customer is idempotent and does not rename; Swahili CSV header and
  an orders export of all 600+ orders (not capped at 100); invalid period; close day with counted cash,
  variance, no double close, no future close, nothing locked; manual mobile money reference unique.
* `test_walk_in.py` (4) — guest walk-in with per-item, per-kg and package lines (TZS 31,000), starts at
  `RECEIVED`, full workflow, collection refused while unpaid then taken with the balance, no commission row,
  counted in the day report as walk-in sales and cash but not as a customer; part payment by mobile money →
  `PARTIAL`, balance owed on the dashboard, over-payment refused, balance in cash at collection, both payments
  in the day report, named walk-in customer has a history; paid in full at drop-off; existing customer by id;
  whole package units; phone orders need a phone; another laundry cannot use this laundry's customer; one
  shared guest record per laundry.

## Commercial model (API, `test_monetization.py`, 8 tests)

The brief's 13-step scenario in one test: an admin creates a TZS 25,000/month plan; a laundry subscribes and gets
a real invoice; finance records the payment (retried with the same idempotency key → one payment); another laundry
gets 90 days complimentary Pro with no invoice and reverts after expiry; a walk-in order completes with no ledger
entry; a Marketplace laundry is approved; an order placed at 5 % (TZS 30,000 → 1,500 / 28,500); the default moves
to 6 % — the next order is charged 6 % while the order placed earlier keeps 5 % although it completes later; a 3 %
laundry rate applies to the next order; the laundry sees its plan and 3 % terms; a refund writes a reversal and
cannot be repeated; the revenue report reconciles, separates subscription money from commission and shows the
laundry's earned / reversed / net; the audit shows the 5.00 → 6.00 change by the finance admin.
Also: no backdated or overlapping rules, promotions need an end; Starter gets 402 for monthly reports, CSV and
manager roles but keeps the end-of-day report, the team limit applies, and an admin entitlement change takes effect
without a deploy; trial → invoice → upgrade credit → downgrade scheduled; unpaid → past due → expired → default plan
with the invoice voided and the owner notified, billing runs idempotent; a pilot with the INVOICE policy ends into an
open invoice and no payment, never touching the Marketplace; Marketplace listings pause and resume with plan
eligibility; operations admins and laundry owners cannot change pricing; owners cannot read other laundries' invoices.

These tests found and fixed: upgrade credit ignored paid periods that had not started yet; a paying laundry upgrading
was put on a new trial, losing its credit; approval checked plan eligibility after changing the status; the audit
stored "6" instead of "6.00"; "days left" rounded down (a new 14-day trial showed 13); the admin login rejected
finance administrators.

## Web

* Vitest: catalog parity EN/SW, no untranslated Swahili, every `t("…")` key exists, no inline language
  conditionals; cart totals/kg/replace/persistence; API client refresh-once, refresh failure, error mapping.
* Provider E2E (`e2e/business.spec.ts`): owner dashboard → *New walk-in order* → three shirts and a trouser
  by tapping tiles → name only → part paid TZS 4,000 → *Create & print slip* → slip shows the order number,
  balance TZS 5,000 and prints → order page → Washing … Ready → *Take TZS 5,000 & hand over* → Completed →
  end-of-day report shows the extra walk-in → CSV downloads → the order is searchable by number.
  Overdue attention item → orders filtered `due=overdue` with "late" badges; pipeline stage → status filter;
  monthly report renders. Staff see orders but no Reports, Payments, Customers, Settings or sales. Pixel 7 in
  Swahili: attention above today's figures, no horizontal scroll.
* These runs found and fixed real bugs: pages read the role/profile outside the workspace frame and got
  nothing (buttons hidden for every role, slip without the laundry's name); order rows marked `role="row"` lost
  their link semantics; the site header/footer styles leaked into the report header and slip; a legacy `.bars`
  rule broke the charts; the payments list showed full totals for part-paid orders.
* Playwright found and drove the fix for one real bug: after OTP, first-time customers skipped the name
  step at checkout (the order would have failed). Fixed in `customer/SignIn.tsx` and page guards.

## Mobile

* Unit: model parsing from the API contract, integer TZS formatting, all statuses in EN and SW, category
  translation rules, greeting; cart totals, per-kg, no mixing laundries, server re-pricing, persistence;
  ARB key parity and no copied English.
* Repository/interceptor: refresh-and-replay, single shared refresh for concurrent 401s, rejected refresh ends
  session, typed translated errors, offline cache fallback, offline without cache, idempotent placement,
  PRICE_CHANGED with fresh quote. (These caught a real bug: the refresh call bypassed the configured
  transport.)
* Widget journeys: onboarding skip; language switch persists; storefront → cart → OTP → checkout → order
  → tracking progression → confirm → review → order again with price change; Swahili tracking; anonymous
  browsing.
* Layout: Home, Explore, storefront with cart bar, Cart, Checkout, Orders, Profile, Privacy at 320×568,
  360×640, 412×915, 430×932 in English and Swahili at 130 % text — no overflow. (Caught a real overflow
  in the cart at 320 px; fixed.)
* **On-device acceptance** (`integration_test/acceptance_test.dart`, phone Z2359, Android 13, USB with
  `adb reverse`, Docker API on PostGIS): onboarding skip → choose Mikocheni → FreshWash → 5 shirts +
  2 trousers → cart TZS 16,000 → phone OTP sign-up → pickup, address, slot, cash → TZS 18,000 → order
  placed (`POST /customer/orders 201`) → FreshWash owner processes via business API → customer pulls to
  refresh and sees "Your clothes are being washed." → delivered + cash recorded → customer confirms →
  review stored and visible on FreshWash → order again rebuilds cart. Passed in 2 m 05 s.
  The device runs led to two UX fixes: tracking actions moved under the headline; bottom sheets open above
  the tab bar.

## Not verified here

* iOS build and run (no macOS).
* Real SMS and mobile-money providers (not integrated in Phase 1; sandbox only).
* Push notifications (no credentials).
* Load/performance testing beyond query plans and bundle sizes.
* Printing on a physical receipt printer (the slip was verified in the browser print path only).

## How to run

```bash
# API
docker compose up -d postgres redis   # tests create a fresh launder_test database on this server
cd apps/api && pip install -r requirements-dev.txt && python -m pytest && ruff check .
# Web
cd apps/web && npm ci && npm run typecheck && npm test && npm run build
docker compose up -d postgres redis api && npx playwright install chromium && npx playwright test
# Mobile (projects/mobile/launder)
flutter analyze && flutter test
adb reverse tcp:8000 tcp:8000
flutter test integration_test/acceptance_test.dart -d <device-id> --dart-define=API_BASE_URL=http://127.0.0.1:8000
flutter build apk --release --dart-define=API_BASE_URL=https://api.launder.co.tz
```
