# Launder

Laundry Business SaaS + Laundry Marketplace for Tanzania. English and Kiswahili.

* **Launder Marketplace** — customers find laundries nearby, order pickup or drop-off, track, pay, review, reorder.
* **Launder Business** — laundries run orders, customers, services, prices, staff and payments. Joining the
  marketplace is a separate application reviewed by Launder.

| Part | Where |
|---|---|
| API (FastAPI, PostgreSQL/PostGIS, Redis) | `apps/api` |
| Web: marketplace, account, Business, Admin (React) | `apps/web` |
| Customer mobile app (Flutter) | `../../mobile/launder` |
| Brand assets generator | `brand/generate.py` |
| Docs | `docs/` — start with [IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md) |

## Run everything with Docker

```bash
cp .env.example .env          # then set JWT_SECRET to a long random value
docker compose up --build     # PostGIS, Redis, API (migrates + seeds in development), web
```

* Web: http://localhost:5173 · API docs: http://localhost:8000/api/docs · Health: `/health`, `/health/ready`

## Run the API outside Docker

The API runs on PostgreSQL + PostGIS only. Start the database containers, then the API on the host:

```bash
docker compose up -d postgres redis      # published on 127.0.0.1:5432 and :6379
cd apps/api
pip install -r requirements-dev.txt
uvicorn app.main:app --port 8000          # migrates and seeds on start (AUTO_SEED defaults to true)

cd apps/web
npm install
npm run dev                               # proxies /api and /media to 127.0.0.1:8000
```

## Demo accounts (development seed only)

| Who | Sign in |
|---|---|
| Customer | Any Tanzanian mobile number; the one-time code is shown in development |
| FreshWash Laundry (marketplace, live) | `owner@freshwash.co.tz` / `Demo123!` · staff `staff@freshwash.co.tz` / `Demo123!` |
| T-Laundry (marketplace application pending review) | `owner@t-laundry.co.tz` / `Demo123!` |
| Other live laundries | `owner@cleanpro.co.tz`, `owner@safilaundry.co.tz`, `owner@bahari.co.tz`, `owner@upangaexpress.co.tz` / `Demo123!` |
| Platform admin | `admin@launder.co.tz` / `Admin123!` |

Business sign-in: `/business/login`. Admin: `/admin/login`. These credentials exist only when `AUTO_SEED=true`,
which the API refuses in production.

## Tests

```bash
cd apps/api && python -m pytest && ruff check .   # needs the postgres container; uses a fresh launder_test database
cd apps/web && npm run typecheck && npm test && npm run build
cd apps/web && npx playwright test        # needs the API running on :8000
cd ../../mobile/launder && flutter analyze && flutter test
```

See [docs/TEST_REPORT.md](docs/TEST_REPORT.md) for the latest results.
