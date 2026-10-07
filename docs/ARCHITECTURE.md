# Launder architecture

```
Customer app (Flutter) ─┐
Web: marketplace, account ─┼──► FastAPI /api/v1 ──► PostgreSQL 16 + PostGIS
Web: Business (app/*)      │         │                Redis (rate limits)
Web: Admin (admin)        ─┘         └── /media (laundry photos)
```

One modular-monolith API serves every client. The customer app, web marketplace, Business SaaS and Admin
share one domain model: a business's marketplace listing, its orders and its customers are the same rows
whichever client touches them.

## API package (`apps/api/app`)

| Module | Responsibility |
|---|---|
| `core/config.py` | Settings from environment (`pydantic-settings`); refuses to start in production with dev defaults |
| `core/security.py` | bcrypt passwords, short-lived JWT access tokens, keyed hashes for refresh tokens and OTP codes |
| `core/errors.py` | One error envelope `{error: {code, message, details, request_id}}` |
| `core/logging.py` | JSON logs, `X-Request-ID`, one access line per request (no bodies or tokens) |
| `core/ratelimit.py` | Redis fixed-window counters (in-process fallback for single-process dev) |
| `domain/` | Order state machine, money rounding, Tanzanian phone normalisation, clock |
| `models/entities.py` | SQLAlchemy models; money as integer TZS, rates/quantities as `Numeric` |
| `services/` | Business rules: auth/OTP/tokens, marketplace discovery & pricing, orders, payments, reviews, business setup, admin decisions, notifications, audit |
| `routers/` | Thin HTTP layer: `auth`, `marketplace` (public), `customer`, `business`, `admin`, `payments` |
| `seed.py` | Idempotent demo data (Dar es Salaam laundries, customers, history) |
| `alembic/` | Migrations; `0001` creates the schema, enables PostGIS and the geography GIST index |

## Key rules

* **Marketplace visibility** — only businesses whose marketplace account is `ACTIVE` (and business `ACTIVE`)
  are ever returned publicly. Registration creates `NOT_ENROLLED`; the business applies when its checklist is
  complete; an admin approves (`PENDING_REVIEW → ACTIVE`), rejects, suspends or reinstates.
* **Orders** — priced on the server from current services; line items snapshot prices. Transitions follow
  `domain/order_states.py` (forward-only, optional stages skippable, pickup legs only for pickup orders,
  completion requires payment). Updates use optimistic concurrency. Customers create orders with an
  `Idempotency-Key`.
* **Money** — whole shillings as integers; commission and per-kg lines computed with `Decimal`,
  half-up rounding. Commission is accrued on the laundry subtotal when a marketplace order completes.
* **Geography** — PostgreSQL uses `ST_DWithin` / `ST_Distance` on `geography(ST_MakePoint(lng, lat))`
  with a matching expression index; SQLite (tests, quick local runs) registers an equivalent haversine function.

## Clients

* `apps/web` — React 19 + Vite. `customer/`, `business/`, `admin/` route trees share `lib/api.ts`
  (sessions per audience, refresh) and EN/SW catalogs. Business and admin bundles load lazily.
* Mobile — Flutter customer app in `projects/mobile/launder`; see [MOBILE_ARCHITECTURE.md](MOBILE_ARCHITECTURE.md).

## Runtime

`docker compose up` runs PostGIS, Redis, the API (migrates on start) and the web app behind nginx
(which proxies `/api` and `/media`). `AUTO_SEED=true` seeds demo data in development only.
