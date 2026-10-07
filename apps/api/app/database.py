import math

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .core.config import settings


class Base(DeclarativeBase):
    pass


def _haversine_km(lat1, lng1, lat2, lng2):
    """SQLite stand-in for PostGIS ST_Distance on geography, used only for local dev and tests."""
    if None in (lat1, lng1, lat2, lng2):
        return None
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(a))


def build_engine(url: str):
    sqlite = url.startswith("sqlite")
    engine = create_engine(url, connect_args={"check_same_thread": False} if sqlite else {}, pool_pre_ping=True)
    if sqlite:
        @event.listens_for(engine, "connect")
        def _sqlite_setup(conn, _):
            conn.create_function("haversine_km", 4, _haversine_km, deterministic=True)
            conn.execute("PRAGMA foreign_keys=ON")

    return engine


engine = build_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
