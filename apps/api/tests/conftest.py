import os

import psycopg

# Tests run against the PostGIS container (`docker compose up -d postgres`). Each session gets a fresh database.
_server = os.environ.get("TEST_DATABASE_SERVER", "launder:launder_dev@localhost:5432")
_name = os.environ.get("TEST_DATABASE_NAME", "launder_test")
with psycopg.connect(f"postgresql://{_server}/postgres", autocommit=True) as _admin:
    _admin.execute(f'DROP DATABASE IF EXISTS "{_name}" WITH (FORCE)')
    _admin.execute(f'CREATE DATABASE "{_name}"')
os.environ.update(DATABASE_URL=f"postgresql+psycopg://{_server}/{_name}", APP_ENV="test", AUTO_SEED="true", EXPOSE_DEV_OTP="true",
                  REDIS_URL="", JWT_SECRET="test-secret-that-is-long-enough-for-hs256-usage")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core import ratelimit  # noqa: E402
from app.main import app  # noqa: E402

FRESHWASH = "freshwash-laundry-mikocheni"
MIKOCHENI = {"lat": -6.7690, "lng": 39.2470}


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:  # runs lifespan: alembic upgrade head + seed
        yield c


@pytest.fixture(autouse=True)
def _reset_limits():
    ratelimit.store.clear()
    yield


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def staff_login(client, email: str, password: str = "Demo123!") -> dict:
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


def customer_login(client, phone: str, name: str | None = "Test Customer") -> dict:
    r = client.post("/api/v1/auth/otp/request", json={"phone": phone})
    assert r.status_code == 200, r.text
    r = client.post("/api/v1/auth/otp/verify", json={"phone": phone, "code": r.json()["dev_code"]})
    assert r.status_code == 200, r.text
    session = r.json()
    if name and session["is_new_user"]:
        assert client.patch("/api/v1/auth/me", json={"full_name": name}, headers=bearer(session["access_token"])).status_code == 200
    return session


@pytest.fixture
def owner(client):
    return bearer(staff_login(client, "owner@freshwash.co.tz")["access_token"])


@pytest.fixture
def admin(client):
    return bearer(staff_login(client, "admin@launder.co.tz", "Admin123!")["access_token"])


def services_by_name(client, slug=FRESHWASH) -> dict:
    store = client.get(f"/api/v1/marketplace/laundries/{slug}").json()
    return {s["name"]: s for g in store["service_groups"] for s in g["services"]}


def first_slot(client, slug=FRESHWASH) -> str:
    slots = client.get(f"/api/v1/marketplace/laundries/{slug}/pickup-slots", params={"days": 7}).json()["slots"]
    assert slots, "seed hours should always yield pickup slots within a week"
    return slots[0]["start"]
