# Launder

Premium bilingual laundry marketplace and business operations platform for Tanzania.

## Run the web app

```bash
cd apps/web
npm install
npm run dev
```

Open `http://localhost:5173`. The customer journey is `/` → `/laundries` → storefront → checkout → tracking. The business dashboard is at `/app`.

## Demo credentials

T-Laundry business owner:

```text
Email: owner@t-laundry.co.tz
Password: Demo123!
```

Launder platform administrator:

```text
Email: admin@launder.co.tz
Password: Admin123!
```

Use `/business/login` for T-Laundry and `/admin/login` for the platform administrator. Credentials are seeded in the local database and are intentionally not displayed or prefilled in either login form. Start the API locally before signing in:

```powershell
cd apps/api
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The admin interface reads protected platform data from the API and persists Marketplace approval, rejection and suspension decisions with an audit record.

## Docker

Copy `.env.example` to `.env`, replace development secrets, then run `docker compose up --build`.

API docs are available at `http://localhost:8000/api/docs`; health is at `/health`.
