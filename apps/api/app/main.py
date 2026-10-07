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
from .routers import admin, auth, business, customer, marketplace, payments

configure_logging()
log = logging.getLogger("launder.app")
MEDIA_DIR = Path(__file__).resolve().parent / "static" / "media"


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
    yield


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


for router in (auth.router, marketplace.router, customer.router, business.router, admin.router, payments.router):
    app.include_router(router, prefix="/api/v1")
