"""Marketplace activation, provider opt-in and commission-free trials. Follows the 17 scenarios of the activation
brief against the real API and database, then the conflict, permission and idempotency rules."""
import uuid
from contextlib import contextmanager
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.database import SessionLocal
from app.domain.clock import as_utc, now_utc
from app.models import (
    Commission,
    CommissionRule,
    MarketplaceAccount,
    MarketplaceAgreement,
    Notification,
    Order,
)
from app.services.commission import CommissionService
from app.services.marketplace_program import MarketplaceProgram

from .conftest import bearer, customer_login, staff_login
from .test_auth import new_phone
from .test_business_admin import register
from .test_monetization import complete

MP = "/api/v1/admin/marketplace"


@pytest.fixture(scope="module")
def finance(client):
    return bearer(staff_login(client, "finance@launder.co.tz", "Admin123!")["access_token"])


@pytest.fixture(scope="module")
def support(client):
    return bearer(staff_login(client, "support@launder.co.tz", "Admin123!")["access_token"])


@contextmanager
def settings(client, finance, **values):
    """Change Marketplace settings for one scenario and always put the defaults back."""
    keys = {f"marketplace_{k}": v for k, v in values.items()}
    current = {s["key"]: s["value"] for s in client.get(f"{MP}/settings", headers=finance).json()["settings"]}
    r = client.put(f"{MP}/settings", headers=finance, json={"values": keys, "reason": "Test scenario"})
    assert r.status_code == 200, r.text
    try:
        yield
    finally:
        client.put(f"{MP}/settings", headers=finance,
                   json={"values": {k: current[k] for k in keys}, "reason": "Restore after test"})


def ready_laundry(client, price=2000):
    """A laundry using Launder Business, with its setup complete but not on the Marketplace."""
    headers, _ = register(client, plan=None)
    client.put("/api/v1/business/profile", headers=headers, json={
        "description": "Family laundry.", "address": "Kawe Beach Rd", "area": "Kawe", "latitude": -6.729, "longitude": 39.228})
    client.put("/api/v1/business/hours", headers=headers,
               json={"days": [{"weekday": d, "opens_at": "07:00", "closes_at": "20:00"} for d in range(7)]})
    services = {}
    for name, p in (("Shirt", price), ("Suit", 10000)):
        services[name] = client.post("/api/v1/business/services", json={"name": name, "price": p}, headers=headers).json()["id"]
    profile = client.get("/api/v1/business/profile", headers=headers).json()
    return headers, profile["slug"], profile["id"], services


def status(client, headers):
    return client.get("/api/v1/business/marketplace", headers=headers).json()


def apply(client, headers, **extra):
    r = client.post("/api/v1/business/marketplace/application", headers=headers,
                    json={"contact_name": "Owner", "pickup_radius_km": 5, "accept_terms": True, **extra})
    assert r.status_code == 200, r.text
    return r.json()


def act(client, headers, bid, action, **body):
    return client.post(f"{MP}/providers/{bid}/{action}", headers=headers, json=body)


def order(client, slug, services, name="Shirt", qty=10):
    customer = bearer(customer_login(client, new_phone(), name="Asha Market")["access_token"])
    return client.post("/api/v1/customer/orders", headers={**customer, "Idempotency-Key": uuid.uuid4().hex},
                       json={"laundry_slug": slug, "items": [{"service_id": services[name], "quantity": qty}],
                             "fulfillment": "DROP_OFF", "payment_method": "CASH"})


def age_trial(bid, days):
    """Move a running trial `days` into the past (agreement and its commission rule together)."""
    with SessionLocal() as db:
        trial = db.scalar(select(MarketplaceAgreement).where(MarketplaceAgreement.business_id == bid,
                                                             MarketplaceAgreement.kind == "TRIAL",
                                                             MarketplaceAgreement.status == "ACTIVE"))
        rule = db.get(CommissionRule, trial.commission_rule_id)
        delta = timedelta(days=days)
        trial.starts_at, trial.ends_at = trial.starts_at - delta, trial.ends_at - delta
        rule.effective_from, rule.effective_to = rule.effective_from - delta, rule.effective_to - delta
        db.commit()


def lifecycle():
    with SessionLocal() as db:
        return MarketplaceProgram(db).run()


def notices(client, headers, kind):
    with SessionLocal() as db:
        owner_id = db.scalar(select(MarketplaceAccount.business_id).where(
            MarketplaceAccount.business_id == client.get("/api/v1/business/profile", headers=headers).json()["id"]))
        from app.models import Business

        user = db.get(Business, owner_id).owner_id
        return [n for n in db.scalars(select(Notification).where(Notification.user_id == user, Notification.kind == kind))]


# ---- 1–5, 9–14, 16: one laundry from walk-in only to standard terms ---------------------------------------------------
def test_provider_first_journey_from_walk_in_to_trial_to_standard_terms(client, admin, finance):
    owner, slug, bid, services = ready_laundry(client)

    # 1–2. Launder Business works without the Marketplace: walk-in orders, completed, never charged.
    view = status(client, owner)
    assert view["status"] == "NOT_ENROLLED" and not view["accepting_orders"]
    assert view["offer"] == {"days": 30, "rate": 0.0, "standard_rate": 5.0, "starts": "WHEN_ORDERS_OPEN"}
    walk = client.post("/api/v1/business/orders", headers=owner, json={"items": [{"service_id": services["Shirt"], "quantity": 4}]})
    assert walk.status_code == 201
    for step in ("WASHING", "READY"):
        client.post(f"/api/v1/business/orders/{walk.json()['id']}/status", json={"status": step}, headers=owner)
    done = client.post(f"/api/v1/business/orders/{walk.json()['id']}/collect", json={"payment": {"method": "CASH"}}, headers=owner)
    assert done.json()["status"] == "COMPLETED"
    assert client.get(f"/api/v1/marketplace/laundries/{slug}").status_code == 404

    # 3. Apply: a draft can be saved incomplete; a free service blocks submission until it has a price.
    zero = client.post("/api/v1/business/services", json={"name": "Free ironing", "price": 0}, headers=owner).json()["id"]
    draft = client.put("/api/v1/business/marketplace/application", headers=owner, json={"contact_name": "Owner"}).json()
    assert draft["status"] == "DRAFT"
    early = client.post("/api/v1/business/marketplace/application", headers=owner,
                        json={"contact_name": "Owner", "pickup_radius_km": 5, "accept_terms": True})
    assert early.status_code == 409 and early.json()["error"]["details"]["missing"] == ["prices"]
    assert client.delete(f"/api/v1/business/services/{zero}", headers=owner).status_code == 204
    assert apply(client, owner)["status"] == "PENDING_REVIEW"
    assert client.get(f"/api/v1/marketplace/laundries/{slug}").status_code == 404

    # 4. Admin reviews: asks for a correction, the laundry resubmits, admin approves.
    detail = client.get(f"{MP}/providers/{bid}", headers=admin).json()
    assert detail["status"] == "PENDING_REVIEW" and detail["trial_offer"]["days"] == 30
    assert all(c["done"] for c in detail["checklist"])
    assert act(client, admin, bid, "request-changes").status_code == 422  # reason required
    assert act(client, admin, bid, "request-changes", reason="Add your TIN").json()["status"] == "CHANGES_REQUESTED"
    assert status(client, owner)["rejection_reason"] == "Add your TIN"
    assert apply(client, owner, tin="123-456-789")["status"] == "PENDING_REVIEW"
    approved = act(client, admin, bid, "approve", reason="Looks good").json()

    # 5. A 30-day commission-free trial starts now (the Marketplace is open).
    assert approved["status"] == "TRIAL_ACTIVE" and approved["accepting_orders"]
    trial = approved["agreement"]
    assert (trial["kind"], trial["rate"], trial["standard_rate"], trial["duration_days"], trial["days_left"]) == \
        ("TRIAL", 0.0, 5.0, 30, 30)
    assert abs((as_utc_iso(trial["ends_at"]) - as_utc_iso(trial["starts_at"])) - timedelta(days=30)) < timedelta(seconds=1)
    assert [h["action"] for h in approved["history"]][:2] == ["APPROVED", "SUBMITTED"]
    assert client.get(f"/api/v1/marketplace/laundries/{slug}").status_code == 200

    # 9. Real Marketplace orders at the trial commission (0 %); the customer pays the normal price.
    placed = order(client, slug, services)
    assert placed.status_code == 201 and placed.json()["total"] == 20000
    complete(client, owner, placed.json()["id"])
    with SessionLocal() as db:
        o = db.get(Order, placed.json()["id"])
        assert (float(o.commission_rate), float(o.commission_standard_rate), o.marketplace_agreement_id) == (0.0, 5.0, trial["id"])
        entry = db.scalar(select(Commission).where(Commission.order_id == o.id))
        assert (entry.amount, entry.waived_amount, entry.agreement_id) == (0, 1000, trial["id"])
    open_order = order(client, slug, services, "Suit", 1).json()  # stays open across the expiry below

    # 10. Walk-in orders remain commission-free during the trial too.
    with SessionLocal() as db:
        assert db.scalar(select(Commission).where(Commission.order_id == walk.json()["id"])) is None

    stats = status(client, owner)["trial_stats"]
    assert (stats["orders"], stats["sales"], stats["commission_charged"]) == (2, 30000, 0)
    assert stats["commission_saved"] == 1000 + 500 and stats["new_customers"] == 2  # settled + still to come

    # 11. Reminders: 7 days before, then 2 days before; repeated runs never repeat them.
    age_trial(bid, 24)  # 6 days left
    lifecycle()
    lifecycle()
    assert [n.data_json.count('"days": 7') for n in notices(client, owner, "MARKETPLACE_TRIAL_ENDING")] == [1]
    age_trial(bid, 5)  # 1 day left
    lifecycle()
    assert len(notices(client, owner, "MARKETPLACE_TRIAL_ENDING")) == 2

    # 12. Expiry without acceptance: new Marketplace orders stop; Business keeps working.
    age_trial(bid, 2)
    stats = lifecycle()
    assert stats["trials_ended"] >= 1
    view = status(client, owner)
    assert view["status"] == "TRIAL_EXPIRED" and not view["accepting_orders"] and view["agreement"] is None
    assert view["last_trial"]["end_reason"] == "EXPIRED" and notices(client, owner, "MARKETPLACE_TRIAL_EXPIRED")
    assert client.get(f"/api/v1/marketplace/laundries/{slug}").status_code == 404
    assert order(client, slug, services).status_code == 404
    assert client.post("/api/v1/business/orders", headers=owner,
                       json={"items": [{"service_id": services["Shirt"], "quantity": 1}]}).status_code == 201
    assert lifecycle()["trials_ended"] == 0  # idempotent

    # 13. Orders placed during the trial still complete, at the trial rate they were placed under.
    complete(client, owner, open_order["id"])
    with SessionLocal() as db:
        late = db.scalar(select(Commission).where(Commission.order_id == open_order["id"]))
        assert (late.amount, late.waived_amount) == (0, 500)

    # 14. The laundry accepts the standard terms and is back on the Marketplace at 5 %.
    accepted = client.post("/api/v1/business/marketplace/accept-terms", headers=owner).json()
    assert accepted["status"] == "ACTIVE" and accepted["accepting_orders"]
    assert accepted["agreement"]["kind"] == "STANDARD" and accepted["commission_rate"] == 5.0
    assert client.post("/api/v1/business/marketplace/accept-terms", headers=owner).status_code == 409
    after = order(client, slug, services)
    assert after.status_code == 201
    complete(client, owner, after.json()["id"])
    with SessionLocal() as db:
        entry = db.scalar(select(Commission).where(Commission.order_id == after.json()["id"]))
        assert (entry.amount, entry.waived_amount, float(entry.rate)) == (1000, 0, 5.0)

    # 16. Reports keep trial, standard and waived commission apart and reconcile with the ledger.
    overview = client.get(f"{MP}/overview", headers=admin).json()
    c = overview["commission"]
    assert c["net"] == c["trial"] + c["standard"] and c["waived"] >= 1500 and c["standard"] >= 1000
    assert overview["trials_converted"] >= 1 and overview["conversion_rate"] is not None
    report = client.get("/api/v1/business/reports/daily", headers=owner).json()  # every plan; all orders were today
    assert report["marketplace"]["commission_waived"] == 1500
    assert report["marketplace"]["commission_trial"] == 0 and report["marketplace"]["commission_standard"] == 1000
    with SessionLocal() as db:
        rows = list(db.scalars(select(Commission).where(Commission.business_id == bid)))
        assert sum(r.amount for r in rows) == 1000 and sum(r.waived_amount for r in rows) == 1500


def as_utc_iso(value):
    from datetime import datetime

    return as_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))


# ---- 6–8: settings apply to new grants only; invitations with individual terms ----------------------------------------
def test_policy_changes_apply_to_new_trials_only_and_invitations_carry_custom_terms(client, admin, finance):
    first, _, first_id, _ = ready_laundry(client)
    apply(client, first)
    act(client, admin, first_id, "approve")
    with settings(client, finance, trial_days=45, trial_rate="2.00"):
        # 6–7. A newly approved laundry gets 45 days at 2 %; the earlier agreement is untouched.
        second, _, second_id, _ = ready_laundry(client)
        assert status(client, second)["offer"]["days"] == 45
        apply(client, second)
        new = act(client, admin, second_id, "approve").json()["agreement"]
        assert (new["duration_days"], new["rate"]) == (45, 2.0)
        old = client.get(f"{MP}/providers/{first_id}", headers=admin).json()["agreement"]
        assert (old["duration_days"], old["rate"]) == (30, 0.0)
        with SessionLocal() as db:
            assert float(CommissionService(db).rule_for(first_id).rate) == 0.0

        # 8. Invite another laundry with individual terms; it confirms and starts without a review queue.
        third, slug, third_id, services = ready_laundry(client)
        assert client.post(f"{MP}/providers/{third_id}/invite", headers=finance,
                           json={"note": "Launch partner", "trial_days": 60, "trial_rate": "1.00"}).status_code == 200
        invited = status(client, third)
        assert invited["status"] == "INVITED" and invited["invitation"]["note"] == "Launch partner"
        assert (invited["offer"]["days"], invited["offer"]["rate"]) == (60, 1.0)
        joined = apply(client, third)
        assert joined["status"] == "TRIAL_ACTIVE"
        assert (joined["agreement"]["source"], joined["agreement"]["duration_days"], joined["agreement"]["rate"]) == \
            ("INVITATION", 60, 1.0)
        placed = order(client, slug, services)
        with SessionLocal() as db:
            assert float(db.get(Order, placed.json()["id"]).commission_rate) == 1.0
    audit = client.get("/api/v1/admin/monetization/audit", params={"entity": "setting"}, headers=finance).json()["items"]
    assert any(a["entity_id"] == "marketplace_trial_days" and a["after"] == {"value": 45} for a in audit)


# ---- 15: suspension and reactivation -------------------------------------------------------------------------------
def test_suspend_and_reactivate_adds_suspended_days_back_to_the_trial(client, admin, support):
    owner, slug, bid, services = ready_laundry(client)
    apply(client, owner)
    act(client, admin, bid, "approve")
    assert act(client, support, bid, "suspend").status_code == 422
    suspended = act(client, support, bid, "suspend", reason="Customer complaints").json()
    assert suspended["status"] == "SUSPENDED" and status(client, owner)["status_reason"] == "Customer complaints"
    assert client.get(f"/api/v1/marketplace/laundries/{slug}").status_code == 404
    assert order(client, slug, services).status_code == 404
    age_trial(bid, 5)  # suspended for the last 3 of 5 trial days
    with SessionLocal() as db:
        account = db.scalar(select(MarketplaceAccount).where(MarketplaceAccount.business_id == bid))
        account.suspended_at = now_utc() - timedelta(days=3)
        db.commit()
    ends_before = as_utc_iso(suspended["agreement"]["ends_at"]) - timedelta(days=5)
    back = act(client, support, bid, "reactivate", reason="Resolved").json()
    assert back["status"] == "TRIAL_ACTIVE" and back["accepting_orders"]
    added = as_utc_iso(back["agreement"]["ends_at"]) - ends_before
    assert timedelta(days=2, hours=23) < added < timedelta(days=3, hours=1)
    assert order(client, slug, services).status_code == 201
    assert [h["action"] for h in back["history"]][:2] == ["REACTIVATED", "SUSPENDED"]


# ---- 17 + launch controls: the Marketplace closed, then a controlled pilot, then public ------------------------------
def test_marketplace_closed_keeps_business_running_and_trials_wait_for_launch(client, admin, finance, owner):
    laundry, slug, bid, services = ready_laundry(client)
    apply(client, laundry)
    with settings(client, finance, mode="OFF"):
        # 17. Discovery and ordering are off; Launder Business is untouched.
        assert client.get("/api/v1/marketplace/laundries").json()["total"] == 0
        assert client.get("/api/v1/marketplace/laundries/freshwash-laundry-mikocheni").status_code == 404
        assert client.get("/api/v1/business/dashboard", headers=owner).status_code == 200
        assert client.post("/api/v1/business/orders", headers=laundry,
                           json={"items": [{"service_id": services["Shirt"], "quantity": 1}]}).status_code == 201
        # Onboarding continues; the trial waits so no days are lost.
        approved = act(client, admin, bid, "approve").json()
        assert approved["status"] == "APPROVED" and approved["agreement"]["status"] == "PENDING_START"
        assert approved["agreement"]["starts_at"] is None and lifecycle()["trials_started"] == 0
        assert not status(client, laundry)["ordering_open"]

        # A controlled pilot: only the launch cohort is open.
        with settings(client, finance, mode="PILOT"):
            assert client.get(f"/api/v1/marketplace/laundries/{slug}").status_code == 404
            joined = client.post(f"{MP}/providers/{bid}/cohort", headers=admin, json={"included": True}).json()
            assert joined["status"] == "TRIAL_ACTIVE" and joined["agreement"]["days_left"] == 30
            assert client.get(f"/api/v1/marketplace/laundries/{slug}").status_code == 200
            assert client.get("/api/v1/marketplace/laundries/freshwash-laundry-mikocheni").status_code == 200  # cohort
    assert client.get("/api/v1/marketplace/laundries/freshwash-laundry-mikocheni").status_code == 200


def test_opening_the_marketplace_starts_waiting_trials(client, admin, finance):
    with settings(client, finance, mode="OFF"):
        laundry, slug, bid, _ = ready_laundry(client)
        apply(client, laundry)
        assert act(client, admin, bid, "approve").json()["status"] == "APPROVED"
    # Restoring PUBLIC runs the lifecycle immediately.
    view = status(client, laundry)
    assert view["status"] == "TRIAL_ACTIVE" and view["agreement"]["days_left"] == 30


# ---- commission conflict resolution ----------------------------------------------------------------------------------
def test_a_special_rate_never_cancels_a_trial_and_a_trial_never_raises_a_special_rate(client, admin, finance):
    owner, _, bid, _ = ready_laundry(client)
    apply(client, owner)
    act(client, admin, bid, "approve")  # 0 % trial
    rules = "/api/v1/admin/monetization/commission/rules"
    assert client.post(rules, headers=finance, json={"scope": "BUSINESS", "business_id": bid, "rate": 3,
                                                     "reason": "Partner"}).status_code == 201
    with SessionLocal() as db:
        assert float(CommissionService(db).rule_for(bid).rate) == 0.0  # the promised trial wins over 3 %
    # Another promotion over the trial dates is refused; the trial's own rule cannot be ended as a rule.
    clash = client.post(rules, headers=finance, json={"scope": "PROMOTION", "business_id": bid, "rate": 1, "reason": "Promo",
                                                      "effective_to": (now_utc() + timedelta(days=5)).isoformat()})
    assert clash.status_code == 409 and clash.json()["error"]["code"] == "OVERLAPPING_RULE"
    with SessionLocal() as db:
        trial_rule = db.scalar(select(CommissionRule).where(CommissionRule.business_id == bid,
                                                            CommissionRule.agreement_id.is_not(None)))
    ended = client.post(f"{rules}/{trial_rule.id}/end", headers=finance, json={"reason": "Oops"})
    assert ended.status_code == 409 and ended.json()["error"]["code"] == "TRIAL_RULE"

    with settings(client, finance, trial_rate="2.00"):
        owner2, _, bid2, _ = ready_laundry(client)
        apply(client, owner2)
        act(client, admin, bid2, "approve")  # 2 % trial
        client.post(rules, headers=finance, json={"scope": "BUSINESS", "business_id": bid2, "rate": 1, "reason": "Partner"})
        with SessionLocal() as db:
            rule = CommissionService(db).rule_for(bid2)
            assert (float(rule.rate), rule.scope) == (1.0, "BUSINESS")  # the better special rate still applies


# ---- admin trial management, one trial per laundry, permissions ------------------------------------------------------
def test_trial_management_is_audited_limited_and_finance_only(client, admin, finance, support):
    owner, _, bid, _ = ready_laundry(client)
    apply(client, owner, accept_post_trial=True)
    assert act(client, support, bid, "approve", trial_days=60).status_code == 403  # custom terms: finance only
    act(client, support, bid, "approve")
    assert client.post(f"{MP}/providers/{bid}/trial/extend", headers=support, json={"days": 7, "reason": "x" * 5}).status_code == 403
    before = client.get(f"{MP}/providers/{bid}", headers=finance).json()["agreement"]
    extended = client.post(f"{MP}/providers/{bid}/trial/extend", headers=finance, json={"days": 14, "reason": "Slow start"})
    assert extended.status_code == 200
    after = extended.json()["agreement"]
    assert after["extensions"] == 1 and as_utc_iso(after["ends_at"]) - as_utc_iso(before["ends_at"]) == timedelta(days=14)
    again = client.post(f"{MP}/providers/{bid}/trial/extend", headers=finance, json={"days": 7, "reason": "More"})
    assert again.status_code == 409 and again.json()["error"]["code"] == "EXTENSION_LIMIT"
    with SessionLocal() as db:
        rule = db.get(CommissionRule, db.get(MarketplaceAgreement, after["id"]).commission_rule_id)
        assert as_utc(rule.effective_to) == as_utc_iso(after["ends_at"])

    # Ending early: reason required; standard terms were accepted in advance, so it converts.
    assert client.post(f"{MP}/providers/{bid}/trial/end", headers=finance, json={"reason": ""}).status_code == 422
    ended = client.post(f"{MP}/providers/{bid}/trial/end", headers=finance, json={"reason": "Asked to switch early"}).json()
    assert ended["status"] == "ACTIVE" and ended["agreement"]["kind"] == "STANDARD"
    assert ended["agreements"][1]["end_reason"] == "ENDED_EARLY"

    # One trial per laundry.
    again = client.post(f"{MP}/providers/{bid}/trial/grant", headers=finance, json={"reason": "Another go"})
    assert again.status_code == 409 and again.json()["error"]["code"] == "TRIAL_ALREADY_USED"
    trail = client.get("/api/v1/admin/monetization/audit", params={"business_id": bid}, headers=finance).json()["items"]
    actions = {a["action"] for a in trail}
    assert {"MARKETPLACE_TRIAL_OFFERED", "MARKETPLACE_TRIAL_STARTED", "MARKETPLACE_TRIAL_EXTENDED",
            "MARKETPLACE_TRIAL_ENDED", "MARKETPLACE_STANDARD_TERMS"} <= actions
    assert all(a["actor"] in ("finance@launder.co.tz", "support@launder.co.tz", "system") for a in trail
               if a["action"].startswith("MARKETPLACE_TRIAL_EXT"))


def test_settings_validation_and_permissions(client, finance, support, owner):
    assert client.put(f"{MP}/settings", headers=support,
                      json={"values": {"marketplace_trial_days": 10}, "reason": "No"}).status_code == 403
    assert client.put(f"{MP}/settings", headers=owner,
                      json={"values": {"marketplace_trial_days": 10}, "reason": "No"}).status_code in (401, 403)
    for bad in ({"marketplace_trial_days": 0}, {"marketplace_trial_rate": "60"}, {"marketplace_mode": "SOMETIMES"},
                {"marketplace_reminder_days": [7, "x"]}, {"marketplace_nope": True}):
        r = client.put(f"{MP}/settings", headers=finance, json={"values": bad, "reason": "Bad value"})
        assert r.status_code in (404, 422), bad
    values = {s["key"]: s["value"] for s in client.get(f"{MP}/settings", headers=support).json()["settings"]}
    assert values["marketplace_trial_days"] == 30 and values["marketplace_trial_rate"] == "0.00"


def test_self_enrollment_can_be_closed_and_providers_only_see_their_own(client, admin, finance):
    owner, _, bid, _ = ready_laundry(client)
    with settings(client, finance, self_enrollment=False):
        view = status(client, owner)
        assert not view["can_apply"]
        r = client.post("/api/v1/business/marketplace/application", headers=owner,
                        json={"contact_name": "Owner", "pickup_radius_km": 5, "accept_terms": True})
        assert r.status_code == 403 and r.json()["error"]["code"] == "ENROLLMENT_CLOSED"
        # Invitations still work while self-enrolment is closed.
        client.post(f"{MP}/providers/{bid}/invite", headers=admin, json={"note": "Join us"})
        assert status(client, owner)["can_apply"]
    assert client.get(f"{MP}/providers/{bid}", headers=owner).status_code in (401, 403)
    assert client.get(f"{MP}/overview", headers=owner).status_code in (401, 403)


def test_one_trial_policy_hides_offers_a_laundry_cannot_get(client, admin, finance):
    owner, _, bid, _ = ready_laundry(client)
    apply(client, owner)
    act(client, admin, bid, "approve")
    age_trial(bid, 31)
    lifecycle()
    assert status(client, owner)["status"] == "TRIAL_EXPIRED"
    with SessionLocal() as db:
        assert MarketplaceProgram(db).trial_offer(bid) is None
    with settings(client, finance, trial_enabled=False):
        other, _, _, _ = ready_laundry(client)
        assert status(client, other)["offer"] is None
