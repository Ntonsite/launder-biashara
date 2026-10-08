"""Commercial model: plans and subscriptions, business terms, pilots, commission rules and ledger, billing cycle, RBAC.
Follows the end-to-end scenario in the monetization brief, then the edge cases."""
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.database import SessionLocal
from app.domain.clock import as_utc, now_utc
from app.models import (
    Business,
    BusinessSubscription,
    Commission,
    MarketplaceAccount,
    Notification,
    Payment,
    PilotEnrollment,
    SubscriptionInvoice,
    SubscriptionPayment,
)
from app.services.billing import PLAN_PAUSE_REASON, BillingService
from app.services.commission import CommissionService
from app.services.entitlements import resolve

from .conftest import bearer, customer_login, staff_login
from .test_auth import new_phone
from .test_business_admin import register

API = "/api/v1/admin/monetization"


@pytest.fixture(scope="module")
def finance(client):
    return bearer(staff_login(client, "finance@launder.co.tz", "Admin123!")["access_token"])


@pytest.fixture(scope="module")
def support(client):
    return bearer(staff_login(client, "support@launder.co.tz", "Admin123!")["access_token"])


def plan(client, finance, code):
    return next(p for p in client.get(f"{API}/plans", headers=finance).json() if p["code"] == code)


def business_id(client, headers):
    return client.get("/api/v1/business/profile", headers=headers).json()["id"]


def live_marketplace_laundry(client, admin):
    """Register → set up → apply → admin approves. Returns (owner headers, slug, business id, services by name)."""
    headers, _ = register(client, plan=None)
    client.put("/api/v1/business/profile", headers=headers, json={
        "description": "Family laundry.", "address": "Kawe Beach Rd", "area": "Kawe", "latitude": -6.729, "longitude": 39.228})
    client.put("/api/v1/business/hours", headers=headers,
               json={"days": [{"weekday": d, "opens_at": "07:00", "closes_at": "20:00"} for d in range(7)]})
    services = {}
    for name, price in (("Shirt", 2000), ("Suit", 10000)):
        services[name] = client.post("/api/v1/business/services", json={"name": name, "price": price}, headers=headers).json()["id"]
    assert client.post("/api/v1/business/marketplace/application", headers=headers,
                       json={"contact_name": "Owner", "pickup_radius_km": 5, "accept_terms": True}).status_code == 200
    profile = client.get("/api/v1/business/profile", headers=headers).json()
    apps = client.get("/api/v1/admin/marketplace-applications", params={"status": "PENDING_REVIEW", "page_size": 100},
                      headers=admin).json()["items"]
    app_id = next(a["id"] for a in apps if a["slug"] == profile["slug"])
    assert client.post(f"/api/v1/admin/marketplace-applications/{app_id}/approve", json={}, headers=admin).status_code == 200
    return headers, profile["slug"], profile["id"], services


def marketplace_order(client, slug, items):
    customer = bearer(customer_login(client, new_phone(), name="Asha Market")["access_token"])
    r = client.post("/api/v1/customer/orders", headers={**customer, "Idempotency-Key": uuid.uuid4().hex},
                    json={"laundry_slug": slug, "items": items, "fulfillment": "DROP_OFF", "payment_method": "CASH"})
    assert r.status_code == 201, r.text
    return r.json()


def complete(client, owner, order_id):
    for status in ("ACCEPTED", "RECEIVED", "READY", "DELIVERED"):
        assert client.post(f"/api/v1/business/orders/{order_id}/status", json={"status": status}, headers=owner).status_code == 200
    client.post(f"/api/v1/business/orders/{order_id}/payments", json={"method": "CASH"}, headers=owner)
    r = client.post(f"/api/v1/business/orders/{order_id}/status", json={"status": "COMPLETED"}, headers=owner)
    assert r.status_code == 200, r.text


def ledger(order_id):
    with SessionLocal() as db:
        return [(c.entry_type, c.amount, float(c.rate)) for c in db.scalars(
            select(Commission).where(Commission.order_id == order_id).order_by(Commission.created_at))]


def default_rule(client, finance, rate, reason):
    r = client.post(f"{API}/commission/rules", headers=finance, json={"scope": "DEFAULT", "rate": rate, "reason": reason})
    assert r.status_code == 201, r.text
    return r.json()


# ---- the brief's scenario -------------------------------------------------------------------------------------------
def test_end_to_end_commercial_scenario(client, admin, finance):
    # 1. A Pro-style plan at TZS 25,000/month created by an administrator (no code change).
    r = client.post(f"{API}/plans", headers=finance, json={
        "code": f"PRO_{uuid.uuid4().hex[:6].upper()}", "name": "Pro 2026", "description": "Test plan", "benefits": ["CRM"],
        "monthly_price": 25000, "annual_price": 250000, "sort_order": 15, "trial_days": 0,
        "features": {"walk_in_orders": True, "customer_crm": True, "advanced_reports": True, "marketplace_eligible": True},
        "reason": "Launch the 2026 Pro plan"})
    assert r.status_code == 201, r.text
    pro = r.json()
    assert pro["current_prices"] == {"MONTHLY": 25000, "ANNUAL": 250000}

    # 2. A laundry subscribes; the invoice is real, nothing is charged until finance records the money.
    owner, _ = register(client, plan=None)
    assert client.get("/api/v1/business/reports/monthly", headers=owner).status_code == 402
    view = client.post("/api/v1/business/subscription", json={"plan_id": pro["id"]}, headers=owner).json()
    assert view["current"]["plan"]["name"] == "Pro 2026" and view["current"]["status"] == "ACTIVE"
    invoice = view["invoices"][0]
    assert (invoice["amount_due"], invoice["status"]) == (25000, "OPEN") and invoice["number"].startswith("INV-")
    assert any(n["kind"] == "invoice_open" for n in view["notices"])
    assert client.get("/api/v1/business/reports/monthly", headers=owner).status_code == 200  # access during payment terms
    key = uuid.uuid4().hex
    ref = f"MP-{uuid.uuid4().hex[:8]}"
    paid = client.post(f"{API}/invoices/{invoice['id']}/payments", headers={**finance, "Idempotency-Key": key},
                       json={"amount": 25000, "method": "MOBILE_MONEY", "reference": ref})
    assert paid.status_code == 201 and paid.json()["status"] == "PAID"
    replay = client.post(f"{API}/invoices/{invoice['id']}/payments", headers={**finance, "Idempotency-Key": key},
                         json={"amount": 25000, "method": "MOBILE_MONEY", "reference": ref})
    assert replay.status_code == 201 and len(replay.json()["payments"]) == 1  # retried request, one payment

    # 3. Another laundry gets 90 days of complimentary Pro — no invoice, access ends on its own.
    guest_owner, _ = register(client, plan=None)
    gid = business_id(client, guest_owner)
    r = client.post(f"{API}/overrides", headers=finance, json={"business_id": gid, "type": "COMPLIMENTARY_PLAN",
                    "plan_id": plan(client, finance, "PRO")["id"], "days": 90, "reason": "Pilot partner"})
    assert r.status_code == 201
    sub = client.get("/api/v1/business/subscription", headers=guest_owner).json()
    assert sub["current"]["source"] == "COMPLIMENTARY" and sub["invoices"] == []
    with SessionLocal() as db:
        assert resolve(db, gid, now_utc() + timedelta(days=91)).source == "DEFAULT"  # expiry reverts to standard terms

    # 4. Walk-in orders never carry commission.
    walk_in = client.post("/api/v1/business/orders", headers=owner, json={"total": 30000}).json()
    for status in ("READY",):
        client.post(f"/api/v1/business/orders/{walk_in['id']}/status", json={"status": status}, headers=owner)
    client.post(f"/api/v1/business/orders/{walk_in['id']}/collect", json={"payment": {"method": "CASH"}}, headers=owner)
    assert ledger(walk_in["id"]) == []

    # 5–7. Marketplace laundry; order placed at the default 5 %.
    mp_owner, slug, mp_id, services = live_marketplace_laundry(client, admin)
    before_change = marketplace_order(client, slug, [{"service_id": services["Suit"], "quantity": 3}])  # 30,000
    preview = client.get(f"{API}/commission/preview", params={"business_id": mp_id, "services": 30000}, headers=finance).json()
    assert (preview["commission"], preview["laundry_amount"]) == (1500, 28500)

    # 8–9. Default goes to 6 %: new orders use it; the order already placed keeps 5 % even though it completes later.
    default_rule(client, finance, 6, "Raise default to 6 %")
    after_change = marketplace_order(client, slug, [{"service_id": services["Suit"], "quantity": 3}])
    complete(client, mp_owner, before_change["id"])
    complete(client, mp_owner, after_change["id"])
    assert ledger(before_change["id"]) == [("EARNED", 1500, 5.0)]
    assert ledger(after_change["id"]) == [("EARNED", 1800, 6.0)]

    # 10–11. Business-specific 3 %.
    r = client.post(f"{API}/commission/rules", headers=finance,
                    json={"scope": "BUSINESS", "business_id": mp_id, "rate": 3, "reason": "Pilot partner rate"})
    assert r.status_code == 201
    third = marketplace_order(client, slug, [{"service_id": services["Suit"], "quantity": 3}])
    complete(client, mp_owner, third["id"])
    assert ledger(third["id"]) == [("EARNED", 900, 3.0)]

    # 12. The laundry sees its plan and its commission terms in plain words.
    mp_view = client.get("/api/v1/business/subscription", headers=mp_owner).json()
    assert mp_view["marketplace"]["commission"]["rate"] == 3.0 and mp_view["current"]["plan"]["name"] == "Starter"
    report = client.get("/api/v1/business/reports/daily", headers=mp_owner).json()
    assert report["marketplace"]["commission_accrued"] == 1500 + 1800 + 900

    # Refund → reversal entry, never an edit; repeating it cannot double count.
    with SessionLocal() as db:
        pay = db.scalar(select(Payment).where(Payment.order_id == third["id"], Payment.status == "PAID"))
    assert client.post(f"/api/v1/admin/payments/{pay.id}/refund", json={"reason": "Damaged suit"}, headers=admin).status_code == 200
    assert client.post(f"/api/v1/admin/payments/{pay.id}/refund", json={"reason": "again"}, headers=admin).status_code == 409
    assert ledger(third["id"]) == [("EARNED", 900, 3.0), ("REVERSED", -900, 3.0)]

    # 13. Revenue reconciles: subscription money and commission are separate streams.
    rev = client.get(f"{API}/revenue", headers=finance).json()
    assert rev["reconciliation"]["matches"] is True
    assert rev["platform_revenue"]["total"] == rev["subscriptions"]["collected"] + rev["marketplace"]["commission_net"]
    row = next(b for b in rev["marketplace"]["by_business"] if b["business_id"] == mp_id)
    assert (row["earned"], row["reversed"], row["net"]) == (4200, 900, 3300)
    assert rev["subscriptions"]["collected"] >= 25000

    audit = client.get(f"{API}/audit", params={"entity": "commission_rule"}, headers=finance).json()["items"]
    raised = next(a for a in audit if a["reason"] == "Raise default to 6 %")
    assert raised["before"]["rate"] == "5.00" and raised["after"]["rate"] == "6.00" and raised["actor"] == "finance@launder.co.tz"
    default_rule(client, finance, 5, "Back to the launch default")  # leave the shared test database as found


# ---- rules ----------------------------------------------------------------------------------------------------------
def test_commission_rules_are_versioned_and_never_overlap(client, finance):
    past = (now_utc() - timedelta(days=1)).isoformat()
    r = client.post(f"{API}/commission/rules", headers=finance, json={"scope": "DEFAULT", "rate": 4, "effective_from": past,
                    "reason": "Backdate attempt"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "BACKDATED_RULE"
    assert client.post(f"{API}/commission/rules", headers=finance,
                       json={"scope": "DEFAULT", "rate": 51, "reason": "Too high"}).status_code == 422
    start = now_utc() + timedelta(days=1)
    promo = {"scope": "PROMOTION", "rate": 2, "effective_from": start.isoformat(),
             "effective_to": (start + timedelta(days=30)).isoformat(), "reason": "Launch month"}
    assert client.post(f"{API}/commission/rules", headers=finance, json={**promo, "effective_to": None}).status_code == 422
    first = client.post(f"{API}/commission/rules", headers=finance, json=promo)
    assert first.status_code == 201 and first.json()["state"] == "SCHEDULED"
    clash = client.post(f"{API}/commission/rules", headers=finance, json={**promo, "reason": "Overlap"})
    assert clash.status_code == 409 and clash.json()["error"]["code"] == "OVERLAPPING_RULE"
    with SessionLocal() as db:
        any_business = db.scalar(select(MarketplaceAccount.business_id))
        assert float(CommissionService(db).rule_for(any_business, start + timedelta(days=2)).rate) in (2.0, 3.0)
    ended = client.post(f"{API}/commission/rules/{first.json()['id']}/end", headers=finance, json={"reason": "Cancelled promo"})
    assert ended.status_code == 200 and ended.json()["state"] in ("ENDED", "SCHEDULED")


def test_plan_features_are_enforced_by_the_api(client, finance):
    owner, _ = register(client, plan=None)  # free default plan
    for method, path, body in (("get", "/api/v1/business/reports/monthly", None),
                               ("get", "/api/v1/business/orders/export.csv", None),
                               ("post", "/api/v1/business/staff", {"full_name": "Kassim", "email": f"c{uuid.uuid4().hex[:6]}@x.co.tz",
                                                                   "password": "Secure123!", "role": "CASHIER"})):
        r = getattr(client, method)(path, headers=owner, **({"json": body} if body else {}))
        assert r.status_code == 402 and r.json()["error"]["code"] == "PLAN_UPGRADE_REQUIRED", path
        assert "Pro" in r.json()["error"]["details"]["available_on"]
    assert client.get("/api/v1/business/reports/daily", headers=owner).status_code == 200  # end of day on every plan
    reports = client.get("/api/v1/business/reports", headers=owner).json()["reports"]
    assert {r["kind"]: r["locked"] for r in reports}["monthly"] is True
    # Staff limit from the plan (Starter: 2).
    for _ in range(2):
        assert client.post("/api/v1/business/staff", headers=owner, json={
            "full_name": "Team Member", "email": f"s{uuid.uuid4().hex[:6]}@x.co.tz", "password": "Secure123!"}).status_code == 201
    over = client.post("/api/v1/business/staff", headers=owner, json={
        "full_name": "One Too Many", "email": f"s{uuid.uuid4().hex[:6]}@x.co.tz", "password": "Secure123!"})
    assert over.status_code == 402 and over.json()["error"]["code"] == "PLAN_LIMIT_REACHED"
    # An admin changes the entitlement — no deploy — and the API follows.
    starter = plan(client, finance, "STARTER")
    client.put(f"{API}/plans/{starter['id']}/features", headers=finance,
               json={"features": {"advanced_reports": True}, "reason": "Trial: reports for everyone"})
    assert client.get("/api/v1/business/reports/monthly", headers=owner).status_code == 200
    client.put(f"{API}/plans/{starter['id']}/features", headers=finance,
               json={"features": {"advanced_reports": False}, "reason": "Trial over"})


def test_upgrade_credits_unused_time_and_downgrade_waits_for_period_end(client, finance):
    owner, _ = register(client, plan=None)
    bid = business_id(client, owner)
    pro, plus = plan(client, finance, "PRO"), plan(client, finance, "BUSINESS_PLUS")
    # Pro has a 14-day trial the first time.
    trial = client.post("/api/v1/business/subscription", json={"plan_id": pro["id"]}, headers=owner).json()
    assert trial["subscription"]["status"] == "TRIALING" and trial["invoices"] == []
    # Trial ends → first invoice; finance records it.
    with SessionLocal() as db:
        BillingService(db).run(now_utc() + timedelta(days=15))
        invoice = db.scalar(select(SubscriptionInvoice).where(SubscriptionInvoice.business_id == bid))
        assert invoice.amount_due == 25000
    client.post(f"{API}/invoices/{invoice.id}/payments", headers=finance, json={"amount": 25000, "method": "CASH"})
    preview = client.get("/api/v1/business/subscription/preview", params={"plan_id": plus["id"]}, headers=owner).json()
    assert preview["takes_effect"] == "NOW" and 0 < preview["credit"] <= 25000 and preview["due_now"] == 60000 - preview["credit"]
    up = client.post("/api/v1/business/subscription", json={"plan_id": plus["id"]}, headers=owner).json()
    new_invoice = next(i for i in up["invoices"] if i["status"] == "OPEN")
    assert new_invoice["amount_due"] == 60000 - preview["credit"] or abs(new_invoice["amount_due"] - (60000 - preview["credit"])) <= 1
    # Paying Business Plus, then choosing Pro: the downgrade is scheduled, not immediate.
    client.post(f"{API}/invoices/{new_invoice['id']}/payments", headers=finance,
                json={"amount": new_invoice["amount_due"], "method": "BANK_TRANSFER"})
    down = client.post("/api/v1/business/subscription", json={"plan_id": pro["id"]}, headers=owner).json()
    assert down["current"]["plan"]["name"] == "Business Plus"
    assert any(n["kind"] == "downgrade_scheduled" for n in down["notices"])


def test_unpaid_invoice_expires_after_grace_and_cycle_is_idempotent(client, finance):
    owner, _ = register(client, plan=None)
    bid = business_id(client, owner)
    plus = plan(client, finance, "BUSINESS_PLUS")
    r = client.post(f"{API}/businesses/{bid}/subscription", headers=finance,
                    json={"plan_id": plus["id"], "reason": "Sales-assisted signup"})
    assert r.status_code == 200
    with SessionLocal() as db:
        sub = db.scalar(select(BusinessSubscription).where(BusinessSubscription.business_id == bid,
                                                           BusinessSubscription.ended_at.is_(None)))
        assert sub.status == "TRIALING"  # Business Plus has a trial the first time
        convert = as_utc(sub.trial_ends_at) + timedelta(minutes=1)
        billing = BillingService(db)
        billing.run(convert)
        billing.run(convert)  # twice: still one invoice
        assert len(list(db.scalars(select(SubscriptionInvoice).where(SubscriptionInvoice.business_id == bid)))) == 1
        billing.run(convert + timedelta(days=8))  # past the 7 payment days
        db.refresh(sub)
        assert sub.status == "PAST_DUE"
        assert resolve(db, bid, convert + timedelta(days=8)).plan.code == "BUSINESS_PLUS"  # still inside grace
        billing.run(convert + timedelta(days=7 + 15))  # payment days + 14 grace days passed
        db.refresh(sub)
        assert sub.status == "EXPIRED"
        invoice = db.scalar(select(SubscriptionInvoice).where(SubscriptionInvoice.business_id == bid))
        assert invoice.status == "VOID"
        assert resolve(db, bid, convert + timedelta(days=30)).source == "DEFAULT"
        kinds = set(db.scalars(select(Notification.kind).where(Notification.user_id == db.get(Business, bid).owner_id)))
        assert {"TRIAL_ENDED", "INVOICE_ISSUED", "INVOICE_OVERDUE", "SUBSCRIPTION_EXPIRED"} <= kinds


def test_pilot_gives_access_then_follows_its_transition_policy(client, admin, finance):
    pro = plan(client, finance, "PRO")
    pilot = client.post(f"{API}/pilots", headers=finance, json={"name": f"Pilot {uuid.uuid4().hex[:4]}", "plan_id": pro["id"],
                        "duration_days": 60, "transition_policy": "INVOICE"}).json()
    owner, _ = register(client, plan=None)
    bid = business_id(client, owner)
    r = client.post(f"{API}/pilots/{pilot['id']}/enrollments", headers=finance, json={"business_ids": [bid]})
    assert r.status_code == 200 and r.json()["enrollments"][0]["status"] == "ACTIVE"
    view = client.get("/api/v1/business/subscription", headers=owner).json()
    assert view["current"]["source"] == "PILOT" and view["notices"][0]["kind"] == "pilot_ending"
    assert view["marketplace"]["status"] == "NOT_ENROLLED"  # a pilot never lists anyone on the Marketplace
    with SessionLocal() as db:
        enrollment = db.scalar(select(PilotEnrollment).where(PilotEnrollment.business_id == bid))
        BillingService(db).run(as_utc(enrollment.ends_at) + timedelta(minutes=1))
        db.refresh(enrollment)
        assert enrollment.status == "ENDED"
        invoice = db.scalar(select(SubscriptionInvoice).where(SubscriptionInvoice.business_id == bid))
        assert invoice.status == "OPEN" and invoice.amount_due == 25000  # offered, not charged
        assert not list(db.scalars(select(SubscriptionPayment).where(SubscriptionPayment.business_id == bid)))


def test_marketplace_follows_plan_eligibility_when_admin_restricts_it(client, admin, finance):
    owner, slug, bid, _ = live_marketplace_laundry(client, admin)
    starter = plan(client, finance, "STARTER")
    client.put(f"{API}/plans/{starter['id']}/features", headers=finance,
               json={"features": {"marketplace_eligible": False}, "reason": "Marketplace for paid plans only"})
    try:
        with SessionLocal() as db:
            BillingService(db).run()
            account = db.scalar(select(MarketplaceAccount).where(MarketplaceAccount.business_id == bid))
            assert (account.status, account.rejection_reason) == ("SUSPENDED", PLAN_PAUSE_REASON)
        assert client.get(f"/api/v1/marketplace/laundries/{slug}").status_code == 404
    finally:
        client.put(f"{API}/plans/{starter['id']}/features", headers=finance,
                   json={"features": {"marketplace_eligible": True}, "reason": "Open to all plans again"})
    with SessionLocal() as db:
        BillingService(db).run()
        assert db.scalar(select(MarketplaceAccount.status).where(MarketplaceAccount.business_id == bid)) == "ACTIVE"


def test_only_finance_roles_change_pricing_and_providers_see_only_their_own(client, admin, finance, support, owner):
    pro = plan(client, support, "PRO")  # read access for operations admins
    assert client.post(f"{API}/plans/{pro['id']}/prices", headers=support,
                       json={"interval": "MONTHLY", "amount": 1, "reason": "Should not work"}).status_code == 403
    assert client.get(f"{API}/plans", headers=owner).status_code == 403
    assert client.post(f"{API}/billing/run", headers=owner).status_code == 403
    # A future price never touches today's price or issued invoices.
    later = (now_utc() + timedelta(days=30)).isoformat()
    r = client.post(f"{API}/plans/{pro['id']}/prices", headers=finance,
                    json={"interval": "MONTHLY", "amount": 30000, "effective_from": later, "reason": "2027 price"})
    assert r.status_code == 201 and r.json()["current_prices"]["MONTHLY"] == 25000
    assert client.post(f"{API}/plans/{pro['id']}/prices", headers=finance,
                       json={"interval": "MONTHLY", "amount": 28000, "effective_from": later, "reason": "Clash"}).status_code == 409
    # Another laundry's invoice is invisible to this owner.
    other_invoice = client.get(f"{API}/invoices", headers=finance).json()["items"][0]
    me = client.get("/api/v1/business/profile", headers=owner).json()["id"]
    if other_invoice["business_id"] != me:
        assert client.get(f"/api/v1/business/invoices/{other_invoice['id']}", headers=owner).status_code == 404
    staff = bearer(staff_login(client, "staff@freshwash.co.tz")["access_token"])
    assert client.get("/api/v1/business/subscription", headers=staff).status_code == 403
