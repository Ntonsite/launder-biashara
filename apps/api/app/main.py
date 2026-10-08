import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session

from .core import ratelimit
from .core.config import settings
from .core.errors import AppError, install_error_handlers
from .core.logging import RequestContextMiddleware, configure_logging
from .database import SessionLocal, get_db
from .routers import (
    admin,
    admin_marketplace,
    admin_monetization,
    auth,
    business,
    business_billing,
    business_reports,
    customer,
    marketplace,
    payments,
)

configure_logging()
log = logging.getLogger("launder.app")
MEDIA_DIR = Path(__file__).resolve().parent / "static" / "media"


def run_billing_once() -> None:
    """One billing pass, guarded by a Postgres advisory lock so several API workers never run it at the same time."""
    from .services.billing import BillingService

    with SessionLocal() as db:
        if not db.scalar(text("SELECT pg_try_advisory_lock(424242)")):
            return
        try:
            stats = BillingService(db).run()
            if any(stats.values()):
                log.info("billing_cycle", extra=stats)
        finally:
            db.execute(text("SELECT pg_advisory_unlock(424242)"))
            db.commit()


async def billing_loop() -> None:
    while True:
        try:
            await asyncio.to_thread(run_billing_once)
        except Exception:  # never let a billing error take the API down; it is logged and retried next tick
            log.exception("billing_cycle_failed")
        await asyncio.sleep(settings.billing_interval_seconds)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.auto_seed:
        # Development convenience only; production runs `alembic upgrade head` as a release step.
        from .migrations import upgrade_to_head
        from .seed import seed

        upgrade_to_head()
        with SessionLocal() as db:
            if seed(db):
                log.info("demo_data_seeded")
    log.info("api_started", extra={"env": settings.app_env, "ratelimit_backend": ratelimit.backend_name()})
    task = asyncio.create_task(billing_loop()) if settings.billing_interval_seconds > 0 else None
    yield
    if task:
        task.cancel()


app = FastAPI(title="Launder API", version="1.1.0", docs_url="/api/docs", openapi_url="/api/openapi.json", lifespan=lifespan)
install_error_handlers(app)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"],
                   allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID", "Accept-Language"],
                   expose_headers=["X-Request-ID", "Retry-After"], allow_credentials=False)
app.mount("/media", StaticFiles(directory=MEDIA_DIR), name="media")


@app.get("/health", tags=["System"])
def health():
    """Liveness: the process is up."""
    return {"status": "healthy"}


@app.get("/health/ready", tags=["System"])
def ready(db: Session = Depends(get_db)):
    """Readiness: database reachable; reports which rate-limit store is active."""
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        raise AppError(503, "NOT_READY", "Database unavailable") from None
    return {"status": "ready", "database": "connected", "ratelimit": ratelimit.backend_name()}


for router in (auth.router, marketplace.router, customer.router, business.router, business_reports.router,
               business_billing.router, admin.router, admin_marketplace.router, admin_monetization.router, payments.router):
    app.include_router(router, prefix="/api/v1")
