# Test report — Phase 1

Run on 2026-10-08, Windows 11, Python 3.12, Node 22, Flutter 3.41.6 / Dart 3.11, Docker 29.
Everything below was actually executed; nothing is extrapolated.

## Summary

| Suite | Result |
|---|---|
| API — pytest (isolated DB, real Alembic migration + seed) | **43 passed** |
| API — ruff | clean |
| API on PostgreSQL 16 + PostGIS 3.4 (Docker) | migration `0001` applied; `ST_DWithin` uses `ix_businesses_geog` (Index Scan); Redis rate limiting active |
| Web — TypeScript (`tsc -b`) | clean |
| Web — Vitest | **12 passed** |
| Web — production build | OK (main bundle 119 KB gzip; business/admin lazy-loaded) |
| Web — Playwright E2E, Chromium, against Docker API | **4 passed** (desktop journey, Swahili desktop + Pixel 7, admin review) |
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

## Web

* Vitest: catalog parity EN/SW, no untranslated Swahili, every `t("…")` key exists, no inline language
  conditionals; cart totals/kg/replace/persistence; API client refresh-once, refresh failure, error mapping.
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

## How to run

```bash
# API
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
