import uuid

from .conftest import bearer, customer_login, staff_login
from .test_auth import new_phone

_TOKENS: dict[str, dict] = {}  # access tokens last 30 minutes; a test run is shorter


def grant_plan(client, business_id: str, plan_code: str = "PRO", days: int = 30) -> None:
    """Give a test laundry complimentary access to a plan through the real admin API (finance role)."""
    if "finance" not in _TOKENS:
        _TOKENS["finance"] = bearer(staff_login(client, "finance@launder.co.tz", "Admin123!")["access_token"])
    finance = _TOKENS["finance"]
    plan = next(p for p in client.get("/api/v1/admin/monetization/plans", headers=finance).json() if p["code"] == plan_code)
    r = client.post("/api/v1/admin/monetization/overrides", headers=finance, json={
        "business_id": business_id, "type": "COMPLIMENTARY_PLAN", "plan_id": plan["id"], "days": days,
        "reason": "Test laundry"})
    assert r.status_code == 201, r.text


def register(client, plan: str | None = "PRO"):
    """A new laundry. By default given Pro (most tests exercise Pro features); plan=None keeps the free default plan."""
    suffix = uuid.uuid4().hex[:8]
    r = client.post("/api/v1/auth/business/register", json={"full_name": "Mwanaisha Kweka", "business_name": f"Kawe Wash {suffix}",
                    "phone": "0715" + suffix[:6].translate(str.maketrans("abcdef", "123456")), "email": f"kawe-{suffix}@example.co.tz",
                    "password": "Secure123!"})
    assert r.status_code == 201, r.text
    headers, user = bearer(r.json()["access_token"]), r.json()["user"]
    if plan:
        grant_plan(client, client.get("/api/v1/business/profile", headers=headers).json()["id"], plan)
    return headers, user


def test_new_business_is_not_listed_until_approved(client, admin):
    headers, _ = register(client)
    slug = client.get("/api/v1/business/profile", headers=headers).json()["slug"]
    status = client.get("/api/v1/business/marketplace", headers=headers).json()
    assert status["status"] == "NOT_ENROLLED"

    # Applying before setup is complete is refused with the missing pieces listed.
    application = {"contact_name": "Mwanaisha Kweka", "pickup_radius_km": 6, "accept_terms": True}
    early = client.post("/api/v1/business/marketplace/application", json=application, headers=headers)
    assert early.status_code == 409 and set(early.json()["error"]["details"]["missing"]) >= {"location", "services", "hours"}

    client.put("/api/v1/business/profile", json={"description": "Family laundry in Kawe.", "address": "Kawe Beach Rd", "area": "Kawe",
               "latitude": -6.7290, "longitude": 39.2280, "pickup_enabled": True, "pickup_fee": 1500}, headers=headers)
    client.put("/api/v1/business/hours", json={"days": [{"weekday": d, "opens_at": "08:00", "closes_at": "18:00"} for d in range(6)]},
               headers=headers)
    client.post("/api/v1/business/services", json={"name": "Shirt", "price": 1800}, headers=headers)
    applied = client.post("/api/v1/business/marketplace/application", json=application, headers=headers)
    assert applied.status_code == 200 and applied.json()["status"] == "PENDING_REVIEW"
    assert client.get(f"/api/v1/marketplace/laundries/{slug}").status_code == 404

    apps = client.get("/api/v1/admin/marketplace-applications", params={"status": "PENDING_REVIEW", "page_size": 100}, headers=admin).json()
    app_id = next(a["id"] for a in apps["items"] if a["slug"] == slug)
    detail = client.get(f"/api/v1/admin/marketplace-applications/{app_id}", headers=admin).json()
    assert all(c["done"] for c in detail["checklist"]) and detail["services"][0]["price"] == 1800

    assert client.post(f"/api/v1/admin/marketplace-applications/{app_id}/approve", json={}, headers=admin).json()["status"] == "ACTIVE"
    assert client.get(f"/api/v1/marketplace/laundries/{slug}").status_code == 200

    # Decisions follow explicit rules.
    assert client.post(f"/api/v1/admin/marketplace-applications/{app_id}/approve", json={}, headers=admin).status_code == 409
    assert client.post(f"/api/v1/admin/marketplace-applications/{app_id}/suspend", json={}, headers=admin).status_code == 422
    assert client.post(f"/api/v1/admin/marketplace-applications/{app_id}/suspend", json={"reason": "Quality complaints"},
                       headers=admin).json()["status"] == "SUSPENDED"
    assert client.get(f"/api/v1/marketplace/laundries/{slug}").status_code == 404

    logs = client.get("/api/v1/admin/audit-logs", headers=admin).json()["items"]
    assert logs[0]["action"] == "MARKETPLACE_SUSPEND" and logs[0]["actor"] == "admin@launder.co.tz"


def test_rbac_is_enforced_server_side(client):
    owner = bearer(staff_login(client, "owner@freshwash.co.tz")["access_token"])
    assert client.get("/api/v1/admin/dashboard", headers=owner).status_code == 403
    assert client.get("/api/v1/admin/dashboard").status_code == 401
    customer = bearer(customer_login(client, new_phone())["access_token"])
    assert client.get("/api/v1/business/profile", headers=customer).status_code == 403


def test_staff_member_processes_orders_but_cannot_manage_team(client):
    staff = bearer(staff_login(client, "staff@freshwash.co.tz")["access_token"])
    orders = client.get("/api/v1/business/orders", headers=staff)
    assert orders.status_code == 200 and orders.json()["total"] > 0
    assert client.post("/api/v1/business/staff", json={"full_name": "New Person", "email": "x@example.co.tz",
                       "password": "Secure123!"}, headers=staff).status_code == 403
    assert client.put("/api/v1/business/profile", json={"pickup_fee": 0}, headers=staff).status_code == 403


def test_owner_adds_staff_who_can_sign_in(client):
    headers, _ = register(client)
    email = f"staff-{uuid.uuid4().hex[:6]}@example.co.tz"
    assert client.post("/api/v1/business/staff", json={"full_name": "Kassim", "email": email, "password": "Secure123!"},
                       headers=headers).status_code == 201
    session = staff_login(client, email, "Secure123!")
    assert session["user"]["role"] == "STAFF" and session["user"]["business_id"]


def test_admin_dashboard_uses_real_commission(client, admin):
    data = client.get("/api/v1/admin/dashboard", headers=admin).json()
    assert data["platform_revenue"] > 0 and data["pending_applications"] >= 1


def test_review_moderation_recomputes_rating(client, admin):
    reviews = client.get("/api/v1/admin/reviews", headers=admin).json()["items"]
    target = next(r for r in reviews if r["status"] == "PUBLISHED")
    before = {x["name"]: x for x in client.get("/api/v1/marketplace/laundries", params={"page_size": 50}).json()["items"]}
    client.post(f"/api/v1/admin/reviews/{target['id']}/hide", headers=admin)
    after = {x["name"]: x for x in client.get("/api/v1/marketplace/laundries", params={"page_size": 50}).json()["items"]}
    assert after[target["business_name"]]["review_count"] == before[target["business_name"]]["review_count"] - 1
    client.post(f"/api/v1/admin/reviews/{target['id']}/publish", headers=admin)
