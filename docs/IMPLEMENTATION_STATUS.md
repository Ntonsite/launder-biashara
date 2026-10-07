# Phase 1 — implementation status

Updated 2026-10-08. "Before" is the state recorded in [PHASE_1_AUDIT.md](PHASE_1_AUDIT.md).

## Customer journey

| Step | Before | Now | Web | Mobile |
|---|---|---|---|---|
| Landing → find laundry | Static | Search goes to marketplace with query; popular laundries from API | ✓ | Home |
| Location / nearby | Missing | GPS ("Near me") or neighbourhood list; PostGIS distance, radius, sorting; denied permission handled | ✓ | ✓ |
| Filters | Static chips | Open now, pickup (within pickup radius), rating, service, distance, sort | ✓ | ✓ (sheet) |
| Map | Missing | OpenStreetMap pins = laundries, pin preview card | — | ✓ |
| Storefront | Hardcoded | API storefront: photos, rating, hours, today, pickup fee, turnaround, grouped services, reviews | ✓ | ✓ |
| Cart | In-memory | Persisted, one laundry per cart, re-priced by the server | ✓ | ✓ |
| Customer auth | Missing | Phone → OTP → name; only when ordering | ✓ | ✓ |
| Checkout | Fake success | Progressive: fulfilment → address → time slot → payment → review; idempotent submit; price-change handling | ✓ | ✓ |
| Confirmation / tracking | Hardcoded | Real order number, timeline from status events, polling with back-off | ✓ | ✓ |
| Payment | Missing | Cash (recorded by laundry); mobile money via sandbox provider + signed webhook; states Pending/Processing/Paid/Failed/Refunded shown | ✓ | ✓ |
| Completion, review | Missing | Customer confirms receipt; review updates rating | ✓ | ✓ |
| Reorder | Link only | Rebuilds cart at today's prices with a list of changes | ✓ | ✓ |
| Favourites, addresses, notifications | Missing | API + mobile screens; web shows addresses at checkout | partial | ✓ |
| English / Swahili | Partial, inline conditionals | Full catalogs, persisted, parity tests | ✓ | ✓ |

## Business journey

| Step | Status |
|---|---|
| Register → onboarding (profile & location, hours, services) | Done — writes real profile/hours/services |
| Services & pricing | Done — categories, per item / per kg, archive instead of delete |
| Staff | Done — owner adds managers/staff; staff can process orders but not manage team or settings |
| Customers | Done — searchable, shows who uses the app |
| Manual (counter) orders | Done — priced from services |
| Order processing | Done — only valid next steps offered; reasons for decline/cancel; cash payment recording |
| Dashboard | Done — real figures (paid revenue, unpaid, today, ready, source mix, commission) |
| Join marketplace | Done — readiness checklist → application → admin review |
| Marketplace orders and commission | Done — same order list; commission accrued on completion |

## Admin

Overview metrics, marketplace applications (detail, approve/reject/suspend/reinstate with rules and reasons),
businesses, orders, customers, payments (refund), reviews (hide/publish with rating recompute), audit trail
with actor and metadata. All enforced by backend RBAC.

## Platform

| Area | Status |
|---|---|
| PostgreSQL + PostGIS | Alembic migration with geography GIST index; validated on `postgis/postgis:16-3.4` |
| Redis | Rate limiting (login, OTP) with in-process fallback |
| Auth | Access 30 min + rotating refresh with reuse detection; OTP 5 min, 5 attempts, 60 s resend, 5 per 15 min |
| Errors, logs, health | Error envelope with request id; JSON logs; `/health`, `/health/ready` |
| Docker | Compose wires env, health checks, migrations on start, nginx proxy for `/api` and `/media` |

## Remaining (non-blocking for Phase 1 demo; required before public launch)

1. **SMS provider** for OTP (e.g. Beem, Africa's Talking). The `console` provider only logs codes; set
   `EXPOSE_DEV_OTP=false` (enforced in production).
2. **Mobile-money aggregator** (e.g. Selcom, AzamPay, ClickPesa) implementing `MobileMoneyProvider` and its
   webhook signature scheme. Until then mobile money is sandbox-only.
3. **Push notifications** — FCM/APNs credentials and a `PushService` implementation. In-app notifications work.
4. **Map tiles** — move from the public OpenStreetMap tile server to a commercial tile provider before launch.
5. **Business photo upload** — covers are seeded files; laundries cannot yet upload their own.
6. **App Links / Universal Links** — host `assetlinks.json` / `apple-app-site-association`; add the iOS
   Associated Domains capability.
7. **iOS build** — not built here (Windows); configuration is in place.
8. **Release signing** — create the upload keystore and `android/key.properties`.
9. **Address on map** — customers can pin current GPS; picking a point on a map is Phase 2.

## Phase 2 (not Phase 1)

Live rider tracking; in-app chat with the laundry; subscription/bundle pricing; loyalty and promo codes;
card payments; multi-branch businesses; business mobile app; payouts and commission invoicing; review
replies; laundry photo galleries; WebSocket/SSE order updates; analytics exports.
