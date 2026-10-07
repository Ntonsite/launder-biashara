# Launder — Phase 1 Audit

Audit date: 2026-10-07. Baseline commit: `4963420 initial commit` (clean tree).

This audit describes the repository **as found**, before the hardening work. What was changed in response is tracked in
[IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) and [TEST_REPORT.md](TEST_REPORT.md).

## 1. Repository shape

| Path | Contents |
|---|---|
| `apps/api` | FastAPI app, ~400 lines total, SQLAlchemy 2 models, SQLite by default |
| `apps/web` | React 19 + Vite + i18next SPA. `App.tsx` (customer, 681 lines), `Business.tsx` (business + admin, 2 202 lines) |
| `docs/` | Architecture, plan, status — **ignored by `.gitignore`, never committed** |
| `docker-compose.yml` | PostGIS 16, Redis 7, api, web |
| `launder.db`, `apps/api/launder.db` | Local SQLite files (ignored, not tracked — OK) |

There is no mobile app, no Alembic, no CI, no frontend tests.

## 2. Status matrix

Legend: DONE · PARTIAL · BROKEN · MOCKED · MISSING · DEAD · DUPLICATED · RISK

### Customer journey (web)

| Step | Status | Finding |
|---|---|---|
| Landing | DONE (visual) | Search box input is ignored; button just navigates |
| Marketplace list | MOCKED | Uses `data.ts` constants; never calls `/marketplace/laundries` |
| Location / nearby | MISSING | "Nearby" button does nothing; no geolocation, no distance from backend |
| Filters | MOCKED | Filter chips are static buttons with no behaviour |
| Storefront | MOCKED | Every slug renders hardcoded "T-Laundry"; services from constants |
| Cart | PARTIAL | In-memory only, lost on navigation/refresh |
| Checkout | MOCKED | Form submit navigates to `/account/orders/LND-24091` without calling the API. Summary hardcodes "5 Shirt / 2 Trouser / TZS 17,500". **Fake success state.** |
| Customer auth / OTP | MISSING | No customer identity at all |
| Tracking | MOCKED | Hardcoded order number and stage index |
| Account / orders | MOCKED | Single hardcoded order card |
| Review | MISSING | |
| Reorder | MOCKED | Link to storefront only |

### Business journey (web + API)

| Step | Status | Finding |
|---|---|---|
| Register business | DONE | Creates owner, business, onboarding, marketplace account |
| Onboarding (9 steps) | PARTIAL | Stored as an opaque JSON blob; branch, hours, location, pickup settings never reach real columns |
| Branch / location | PARTIAL | `Branch` model exists, no API to manage it |
| Services & pricing | DONE | CRUD with ownership checks; UI also writes a localStorage copy (DUPLICATED state) |
| Operating hours | MISSING | No model |
| Staff | MISSING | No staff model/roles beyond owner; `BRANCH_MANAGER` role is referenced but cannot be created; no `User.business_id` |
| Customers | PARTIAL | List/search API; UI is `GenericModule` placeholder |
| Manual order | PARTIAL | Accepts arbitrary `total` from the client, no line items |
| Order processing | MOCKED | `OrderDetail` is local `useState("WASHING")`; no status endpoint exists |
| Payments | MISSING | `payment_status` column only; `/app/payments` is a placeholder |
| Dashboard / analytics | PARTIAL | Analytics endpoint sums *all* order totals incl. unpaid/cancelled |
| Join marketplace | MISSING | No apply endpoint; status page is read-only. Seeded business is pre-set to `PENDING_REVIEW` |
| Marketplace order receipt | BROKEN | Public `POST /orders` creates an order for **any** business by slug, including non-marketplace ones |
| Commission | MISSING | Admin "platform revenue" = 5 % of all GMV, computed on the fly from unpaid orders |

### Admin

| Area | Status | Finding |
|---|---|---|
| Login | DONE | Shared email/password login, role-checked by `require_admin` |
| Dashboard | PARTIAL | GMV counts unpaid and walk-in orders |
| Businesses / customers / orders / reviews | PARTIAL | Unpaginated, read-only |
| Applications | PARTIAL | Approve/reject/suspend with audit log; **no state preconditions** (can "approve" a `NOT_ENROLLED` or `REJECTED` account; can suspend a pending one) |
| Review moderation | MISSING | |
| Payments | MISSING | |
| Audit trail | PARTIAL | No actor name, no metadata, unpaginated |

## 3. Backend findings

| # | Area | Severity | Finding |
|---|---|---|---|
| B1 | Orders | **High / RISK** | `POST /api/v1/orders` is unauthenticated and trusts client `total`. Anyone can create orders with any price against any business. |
| B2 | Orders | High | No order items. Totals cannot be audited or reordered. |
| B3 | Orders | High | No state machine; no status-change endpoint at all. |
| B4 | Orders | Medium | Order numbers derived from `count(*)` → race-prone and collides across the two generators (`LND-24091+n` vs `LND-26000+n`). |
| B5 | Money | Medium | Prices are `Integer` (safe), but `rating`, `commission_rate` are `Float`; commission computed with float `gmv*.05`. |
| B6 | Auth | High | No refresh tokens; 8-hour access tokens; no logout/revocation. |
| B7 | Auth | High | No customer authentication / OTP. |
| B8 | Auth | Medium | `JWT_SECRET` silently defaults to a known string; no production guard. |
| B9 | Auth | Medium | No login rate-limiting or lockout. |
| B10 | RBAC | Medium | `require_business` allows `BRANCH_MANAGER`, but `owned()` looks up the business by `owner_id`, so managers always get 404. |
| B11 | Marketplace | High | No apply/verify flow; admin decisions have no precondition checks. |
| B12 | Marketplace | High | Discovery returns no location, distance, hours, price or cover; ignores lat/lng entirely. PostGIS is provisioned but unused. |
| B13 | Data | High | `seed_database()` and `create_all()` run **on import of `app.main`** in every environment. No Alembic. |
| B14 | Tests | Medium | Tests run against the developer's `launder.db`; state leaks between runs. |
| B15 | Errors | Low | Inconsistent error bodies; no request IDs; no structured logs. |
| B16 | Config | Low | CORS origins hard-coded; `pydantic-settings` listed but unused. |
| B17 | Docker | Medium | API container gets no `DATABASE_URL`/`JWT_SECRET` (compose has no `env_file`), so it silently runs on SQLite inside the container. Redis is started but never used. |
| B18 | Reviews | Medium | `Review` has no business or customer link; business `rating` is a static seed value. |
| B19 | Indexes | Low | Missing FK index on `orders.customer_id`; no composite index for business order listing. |

## 4. Web findings

| # | Finding |
|---|---|
| W1 | API base URL `http://127.0.0.1:8000` hard-coded in ~20 places; breaks in Docker (nginx proxies `/api/` but code bypasses it). |
| W2 | Customer flow fully mocked (see §2). Fake success on checkout. |
| W3 | Localisation: catalogs exist, but `Business.tsx` uses many inline `sw ? "…" : "…"` conditions and hard-coded English; storefront uses `i18n.language === "sw" ? s.sw : s.name` — translating user-generated service names. |
| W4 | Broken glyph strings in checkout (`x!x! +255`, `x` radio labels) — encoding damage. |
| W5 | All dependencies pinned to `latest` — non-reproducible builds. |
| W6 | No tests (`vitest run` finds nothing). |
| W7 | Tokens in `localStorage` — acceptable for this SPA in Phase 1 given no third-party scripts, but documented. |
| W8 | `dist/` and `tsconfig.tsbuildinfo` present locally (ignored — OK). |

## 5. Localisation

- Web: i18next with `en`/`sw` JSON catalogs and persisted preference — **good foundation, kept**.
- Gaps: business/admin screens bypass catalogs; some Swahili is literal.
- Mobile: none.

## 6. Security summary

Highest risks, in order: B1 (unauthenticated priced order creation), B6/B7 (token lifecycle, no customer auth),
B11 (marketplace approvals without preconditions), B13 (seed on import incl. production), B8 (default secret),
B17 (compose ignores secrets).

## 7. What is good and was preserved

- Layered API layout (core / models / schemas / repositories / services / routers).
- Ownership checks on service CRUD (`Service.business_id == b.id`).
- bcrypt password hashing; role dependency pattern; audit log table.
- The web design language (palette `#0F4C81`, `#14B8A6`, warm neutrals) and i18n catalogs.
- Business onboarding and services screens.

## 8. Plan of record

1. Backend: Alembic, settings, seed CLI, state machine, items/totals in server, customer OTP auth with refresh rotation,
   marketplace apply → review → approve, PostGIS distance search (SQLite fallback for tests), reviews/ratings,
   payments abstraction, commissions, favourites, addresses, notifications, isolated test DB.
2. Web: central API client, real customer journey (discovery → order → tracking → review → reorder), real business
   order processing and marketplace application, admin preconditions.
3. Mobile: new Flutter customer app at `C:\Users\ntonsite.mwamlima\projects\mobile\launder` (location requested by the
   product owner) consuming the same `/api/v1`.
