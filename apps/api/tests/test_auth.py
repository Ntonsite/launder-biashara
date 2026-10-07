import random

from app.core.security import create_access_token

from .conftest import bearer, customer_login, staff_login


def new_phone() -> str:
    return "+2557" + "".join(str(random.randint(0, 9)) for _ in range(8))


def test_health_and_readiness(client):
    assert client.get("/health").json()["status"] == "healthy"
    assert client.get("/health/ready").json()["database"] == "connected"


def test_staff_login_returns_token_pair(client):
    session = staff_login(client, "owner@freshwash.co.tz")
    assert session["refresh_token"] and session["access_token"]
    assert session["user"]["role"] == "BUSINESS_OWNER" and session["user"]["business_id"]


def test_invalid_login_is_rejected_with_error_envelope(client):
    r = client.post("/api/v1/auth/login", json={"email": "owner@freshwash.co.tz", "password": "incorrect!"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "INVALID_CREDENTIALS"
    assert "request_id" in r.json()["error"]


def test_login_is_rate_limited_after_repeated_failures(client):
    for _ in range(8):
        client.post("/api/v1/auth/login", json={"email": "owner@cleanpro.co.tz", "password": "wrong-password"})
    r = client.post("/api/v1/auth/login", json={"email": "owner@cleanpro.co.tz", "password": "Demo123!"})
    assert r.status_code == 429


def test_refresh_rotates_and_detects_reuse(client):
    session = staff_login(client, "owner@safilaundry.co.tz")
    first = session["refresh_token"]
    rotated = client.post("/api/v1/auth/refresh", json={"refresh_token": first})
    assert rotated.status_code == 200
    second = rotated.json()["refresh_token"]
    assert second != first
    # Replaying the rotated token is treated as theft and kills the whole family, including the new token.
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": first}).status_code == 401
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": second}).status_code == 401


def test_logout_revokes_refresh_token(client):
    session = staff_login(client, "owner@bahari.co.tz")
    assert client.post("/api/v1/auth/logout", json={"refresh_token": session["refresh_token"]}).status_code == 204
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": session["refresh_token"]}).status_code == 401


def test_customer_otp_signup_links_profile(client):
    phone = new_phone()
    session = customer_login(client, phone, name="Amina Ali")
    me = client.get("/api/v1/auth/me", headers=bearer(session["access_token"])).json()
    assert me["role"] == "CUSTOMER" and me["phone"] == phone and me["name"] == "Amina Ali"


def test_otp_accepts_local_phone_formats(client):
    digits = new_phone()[4:]
    r = client.post("/api/v1/auth/otp/request", json={"phone": "0" + digits[:3] + " " + digits[3:]})
    assert r.status_code == 200 and r.json()["phone"] == "+255" + digits


def test_invalid_phone_is_rejected(client):
    r = client.post("/api/v1/auth/otp/request", json={"phone": "+254712345678"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_PHONE"


def test_otp_resend_cooldown(client):
    phone = new_phone()
    assert client.post("/api/v1/auth/otp/request", json={"phone": phone}).status_code == 200
    r = client.post("/api/v1/auth/otp/request", json={"phone": phone})
    assert r.status_code == 429 and r.json()["error"]["code"] == "OTP_RESEND_TOO_SOON"


def test_wrong_otp_counts_attempts_then_locks(client):
    phone = new_phone()
    code = client.post("/api/v1/auth/otp/request", json={"phone": phone}).json()["dev_code"]
    wrong = "000000" if code != "000000" else "111111"
    for remaining in (4, 3, 2, 1, 0):
        r = client.post("/api/v1/auth/otp/verify", json={"phone": phone, "code": wrong})
        assert r.status_code == 400 and r.json()["error"]["details"]["attempts_remaining"] == remaining
    # Even the right code no longer works once the challenge is locked.
    assert client.post("/api/v1/auth/otp/verify", json={"phone": phone, "code": code}).status_code == 400


def test_customer_cannot_use_password_login_or_business_api(client):
    session = customer_login(client, new_phone())
    assert client.get("/api/v1/business/orders", headers=bearer(session["access_token"])).status_code == 403
    assert client.get("/api/v1/admin/dashboard", headers=bearer(session["access_token"])).status_code == 403


def test_expired_access_token_is_reported_clearly(client, monkeypatch):
    from app.core import security
    monkeypatch.setattr(security.settings, "access_token_minutes", -1, raising=False)
    token = create_access_token("someone", "CUSTOMER")
    r = client.get("/api/v1/auth/me", headers=bearer(token))
    assert r.status_code == 401 and r.json()["error"]["code"] == "TOKEN_EXPIRED"


def test_refresh_token_cannot_be_used_as_access_token(client):
    session = staff_login(client, "owner@upangaexpress.co.tz")
    assert client.get("/api/v1/auth/me", headers=bearer(session["refresh_token"])).status_code == 401
