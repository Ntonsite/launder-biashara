"""Provider workspace: dashboard figures, periods and comparisons, due dates, roles, CRM, reports, exports, day close."""
import csv
import io
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import update

from app.database import SessionLocal
from app.domain.clock import LOCAL_TZ, now_utc
from app.domain.periods import PeriodError, resolve
from app.models import Order, Payment

from .conftest import bearer, staff_login
from .test_business_admin import register


# ---- periods ---------------------------------------------------------------------------------------------------
def at_local(y, m, d, h=12, minute=0) -> datetime:
    return datetime(y, m, d, h, minute, tzinfo=LOCAL_TZ).astimezone(UTC)


def test_month_to_date_compares_with_same_days_of_previous_month():
    p = resolve("this_month", now=at_local(2026, 3, 31, 18))
    assert (p.start_date, p.end_date, p.in_progress) == (date(2026, 3, 1), date(2026, 3, 31), True)
    # 30 days and 18 hours into March; February only has 28 days, so the comparison stops at the end of February.
    assert p.prev_start == at_local(2026, 2, 1, 0) and p.prev_until == at_local(2026, 3, 1, 0)
    p = resolve("this_month", now=at_local(2026, 10, 8, 9, 30))
    assert p.prev_start == at_local(2026, 9, 1, 0) and p.prev_until == at_local(2026, 9, 8, 9, 30)


def test_finished_month_compares_with_whole_previous_month():
    p = resolve("last_month", now=at_local(2026, 3, 10))
    assert (p.start_date, p.end_date, p.in_progress) == (date(2026, 2, 1), date(2026, 2, 28), False)
    assert p.prev_start == at_local(2026, 1, 1, 0) and p.prev_until == at_local(2026, 2, 1, 0)


def test_today_compares_with_same_weekday_last_week_up_to_now():
    p = resolve("today", now=at_local(2026, 10, 8, 15))
    assert p.compare_to == "previous_day_same_weekday"
    assert p.prev_start == at_local(2026, 10, 1, 0) and p.prev_until == at_local(2026, 10, 1, 15)


def test_weeks_start_on_monday_and_custom_ranges_are_validated():
    p = resolve("this_week", now=at_local(2026, 10, 8))  # a Thursday
    assert p.start_date == date(2026, 10, 5) and p.end_date == date(2026, 10, 11)
    last = resolve("last_week", now=at_local(2026, 10, 8))
    assert last.start_date == date(2026, 9, 28) and not last.in_progress
    custom = resolve("custom", date(2026, 9, 1), date(2026, 9, 10), now=at_local(2026, 10, 8))
    assert custom.days == 10 and custom.prev_start == at_local(2026, 8, 22, 0)
    for bad in [("custom", None, None), ("custom", date(2026, 9, 10), date(2026, 9, 1)),
                ("custom", date(2024, 1, 1), date(2026, 1, 1)), ("fortnight", None, None)]:
        with pytest.raises(PeriodError):
            resolve(*bad)


# ---- a fresh laundry with known numbers ------------------------------------------------------------------------
def setup_laundry(client):
    headers, _ = register(client)
    services = {}
    for name, price, hours in [("Shirt", 2000, 24), ("Suit", 8000, 48)]:
        r = client.post("/api/v1/business/services", json={"name": name, "price": price, "turnaround_hours": hours},
                        headers=headers)
        services[name] = r.json()["id"]
    return headers, services


def counter_order(client, headers, services, lines, **extra):
    phone = extra.pop("phone", "0754" + str(uuid.uuid4().int)[:6])
    body = {"customer_name": extra.pop("name", "Walk-in Customer"), "phone": phone,
            "items": [{"service_id": services[n], "quantity": q} for n, q in lines], **extra}
    r = client.post("/api/v1/business/orders", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def set_order(order_id: str, **values):
    with SessionLocal() as db:
        db.execute(update(Order).where(Order.id == order_id).values(**values))
        db.commit()


def test_new_laundry_sees_setup_checklist_not_zeros(client):
    headers, _ = register(client)
    data = client.get("/api/v1/business/dashboard", headers=headers).json()
    assert data["has_orders"] is False and "performance" not in data
    steps = {s["key"]: s["done"] for s in data["first_run"]}
    assert steps["business"] and not steps["services"] and not steps["first_order"]


def test_dashboard_today_separates_sales_collections_and_outstanding(client):
    headers, services = setup_laundry(client)
    a = counter_order(client, headers, services, [("Shirt", 5)])  # 10,000, due in 24 h
    b = counter_order(client, headers, services, [("Shirt", 2), ("Suit", 1)], discount=1000)  # 12,000 - 1,000
    assert b["total"] == 11000
    detail = client.get(f"/api/v1/business/orders/{b['id']}", headers=headers).json()
    created = datetime.fromisoformat(detail["created_at"])
    # Promise defaults to the slowest service: the suit's 48 hours.
    assert abs((datetime.fromisoformat(detail["due_at"]) - created) - timedelta(hours=48)) < timedelta(seconds=5)
    assert client.post(f"/api/v1/business/orders/{a['id']}/payments", json={"method": "CASH"}, headers=headers).status_code == 200
    # An order taken two days ago and paid today counts as collected today, not as sales today.
    old = counter_order(client, headers, services, [("Suit", 2)])
    set_order(old["id"], created_at=now_utc() - timedelta(days=2))
    client.post(f"/api/v1/business/orders/{old['id']}/payments", json={"method": "MOBILE_MONEY", "reference": f"MP{uuid.uuid4().hex[:8]}"},
                headers=headers)

    data = client.get("/api/v1/business/dashboard", headers=headers).json()
    today = data["today"]
    assert today["orders"]["value"] == 2 and today["sales"]["value"] == 21000
    assert today["collected"] == 10000 + 16000
    assert today["outstanding"] == {"count": 1, "amount": 11000}
    assert today["orders"]["change_pct"] is None  # nothing to compare with yet
    assert data["first_run"] is None and data["performance"]["sales"]["value"] >= 21000

    report = client.get("/api/v1/business/reports/daily", headers=headers).json()
    assert report["money"]["sales"] == 21000 and report["money"]["discounts"] == 1000
    assert report["payments"]["CASH"]["amount"] == 10000 and report["payments"]["MOBILE_MONEY"]["amount"] == 16000
    assert report["day_book"]["opening"] == 1 and report["day_book"]["new"] == 2 and report["day_book"]["carried_forward"] == 3


def test_overdue_and_due_today_drive_attention_and_order_views(client):
    headers, services = setup_laundry(client)
    late = counter_order(client, headers, services, [("Shirt", 1)])
    soon = counter_order(client, headers, services, [("Shirt", 1)])
    set_order(late["id"], due_at=now_utc() - timedelta(hours=3))
    end_of_today = resolve("today").end
    set_order(soon["id"], due_at=min(now_utc() + timedelta(minutes=30), end_of_today - timedelta(minutes=1)))

    attention = {a["key"]: a for a in client.get("/api/v1/business/dashboard", headers=headers).json()["attention"]}
    assert attention["overdue"]["count"] == 1 and attention["overdue"]["query"] == {"due": "overdue"}
    assert attention["due_today"]["count"] == 1 and attention["outstanding"]["amount"] == 4000

    overdue = client.get("/api/v1/business/orders", params={"due": "overdue"}, headers=headers).json()["items"]
    assert [o["id"] for o in overdue] == [late["id"]] and overdue[0]["due_state"] == "OVERDUE"
    assert overdue[0]["items"] == [{"name": "Shirt", "quantity": 1.0, "pricing_model": "PER_ITEM"}]
    counts = client.get("/api/v1/business/orders/counts", headers=headers).json()
    assert counts["due_overdue"] == 1 and counts["in_progress"] == 2 and counts["all"] == 2

    # Ready late counts against on-time performance; moving the promise is audited and validated.
    for step in ("WASHING", "READY"):  # walk-ins start at RECEIVED
        assert client.post(f"/api/v1/business/orders/{late['id']}/status", json={"status": step}, headers=headers).status_code == 200
    ops = client.get("/api/v1/business/reports/daily", headers=headers).json()["operations"]
    assert ops["ready_late"] == 1 and ops["on_time_rate"] == 0.0
    new_due = (now_utc() + timedelta(days=1)).isoformat()
    assert client.patch(f"/api/v1/business/orders/{soon['id']}", json={"due_at": new_due}, headers=headers).status_code == 200


def test_comparisons_appear_only_with_enough_history(client):
    headers, services = setup_laundry(client)
    today = resolve("today")
    # Inside last week's comparison window whatever the time of day the test runs.
    last_week = today.prev_start + (today.prev_until - today.prev_start) / 2
    for _ in range(6):
        o = counter_order(client, headers, services, [("Shirt", 1)])
        set_order(o["id"], created_at=last_week)
    counter_order(client, headers, services, [("Shirt", 3)])
    data = client.get("/api/v1/business/dashboard", headers=headers).json()["today"]
    # Same weekday last week, up to the same time: 6 orders, enough to compare.
    assert data["orders"]["previous"] == 6 and data["orders"]["change_pct"] == pytest.approx(-83.3)


def test_roles_see_and_do_only_their_part(client):
    owner, services = setup_laundry(client)
    accounts = {}
    for role in ("BRANCH_MANAGER", "CASHIER", "STAFF", "DRIVER"):
        email = f"{role.lower()}-{uuid.uuid4().hex[:6]}@example.co.tz"
        assert client.post("/api/v1/business/staff", json={"full_name": role.title(), "email": email, "password": "Secure123!",
                                                           "role": role}, headers=owner).status_code == 201
        accounts[role] = bearer(staff_login(client, email, "Secure123!")["access_token"])
    manager, cashier, staff, driver = (accounts[r] for r in ("BRANCH_MANAGER", "CASHIER", "STAFF", "DRIVER"))

    # Cashier takes the order and the money; staff do the washing; nobody else sees the books.
    order = counter_order(client, cashier, services, [("Shirt", 2)])
    assert client.post("/api/v1/business/orders", json={"customer_name": "X Y", "phone": "0754000111",
                       "items": [{"service_id": services["Shirt"], "quantity": 1}]}, headers=staff).status_code == 403
    assert client.post(f"/api/v1/business/orders/{order['id']}/status", json={"status": "WASHING"},
                       headers=cashier).status_code == 403
    for step in ("WASHING", "READY"):  # walk-ins start at RECEIVED
        assert client.post(f"/api/v1/business/orders/{order['id']}/status", json={"status": step},
                           headers=staff).status_code == 200
    assert client.post(f"/api/v1/business/orders/{order['id']}/payments", json={"method": "CASH"},
                       headers=staff).status_code == 403
    assert client.post(f"/api/v1/business/orders/{order['id']}/payments", json={"method": "CASH"},
                       headers=cashier).status_code == 200
    detail = client.get(f"/api/v1/business/orders/{order['id']}", headers=cashier).json()
    assert detail["allowed_next"] == ["DELIVERED"]

    staff_dash = client.get("/api/v1/business/dashboard", headers=staff).json()
    assert "sales" not in staff_dash["today"] and "performance" not in staff_dash
    assert all(a["key"] not in ("outstanding", "payments_stuck") for a in staff_dash["attention"])
    assert client.get("/api/v1/business/customers", headers=staff).status_code == 403
    for who in (staff, cashier, driver):
        assert client.get("/api/v1/business/reports/daily", headers=who).status_code == 403
    assert client.get("/api/v1/business/reports/daily", headers=manager).status_code == 200
    assert client.get("/api/v1/business/reports/monthly", headers=manager).status_code == 403
    assert "performance" not in client.get("/api/v1/business/dashboard", headers=manager).json()
    assert [r["kind"] for r in client.get("/api/v1/business/reports", headers=manager).json()["reports"]] == \
        ["daily", "weekly", "orders", "payments"]
    caps = client.get("/api/v1/business/profile", headers=cashier).json()["capabilities"]
    assert "orders.create" in caps and "reports.operational" not in caps

    # Drivers only see pickup work and cannot touch a drop-off order.
    assert client.get("/api/v1/business/orders", headers=driver).json()["total"] == 0
    assert client.get(f"/api/v1/business/orders/{order['id']}", headers=driver).status_code == 404


def test_customer_crm_profiles_and_segments(client):
    headers, services = setup_laundry(client)
    phone = "0754" + str(uuid.uuid4().int)[:6]
    for qty in (1, 2, 3):
        counter_order(client, headers, services, [("Shirt", qty)], phone=phone, name="Grace Mushi")
    once = counter_order(client, headers, services, [("Suit", 1)], name="Once Only")
    customers = client.get("/api/v1/business/customers", params={"sort": "spend"}, headers=headers).json()["items"]
    grace = next(c for c in customers if c["name"] == "Grace Mushi")
    assert (grace["orders"], grace["spend"], grace["average_order"], grace["segment"]) == (3, 12000, 4000, "FREQUENT")
    assert grace["outstanding"] == 12000
    assert client.get("/api/v1/business/customers", params={"segment": "new"}, headers=headers).json()["total"] == 1
    detail = client.get(f"/api/v1/business/customers/{grace['id']}", headers=headers).json()
    assert detail["preferred_services"][0] == {"name": "Shirt", "orders": 3, "quantity": 6.0}
    assert len(detail["recent_orders"]) == 3 and once["id"] not in [o["id"] for o in detail["recent_orders"]]

    added = client.post("/api/v1/business/customers", json={"name": "New Person", "phone": "0713" + phone[-6:],
                        "notes": "Prefers no starch"}, headers=headers)
    assert added.status_code == 201 and added.json()["orders"] == 0 and added.json()["notes"] == "Prefers no starch"
    again = client.post("/api/v1/business/customers", json={"name": "Other Name", "phone": "0713" + phone[-6:]}, headers=headers)
    assert again.json()["id"] == added.json()["id"] and again.json()["name"] == "New Person"


def test_reports_export_csv_with_header_and_all_rows(client, owner):
    r = client.get("/api/v1/business/reports/monthly/export.csv", params={"period": "last_month", "lang": "sw"}, headers=owner)
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(r.text.lstrip("﻿"))))
    assert rows[0] == ["Ripoti ya biashara ya mwezi"] and rows[1] == ["Dobi", "FreshWash Laundry"]
    assert rows[3][0] == "Kipindi" and any(row and row[0] == "Kwa siku" or row[:1] == ["Tarehe"] for row in rows)

    export = client.get("/api/v1/business/orders/export.csv", headers=owner)
    lines = list(csv.reader(io.StringIO(export.text.lstrip("﻿"))))
    total = client.get("/api/v1/business/orders", params={"page_size": 5}, headers=owner).json()["total"]
    assert total > 100 and len(lines) - 7 == total  # 6 header lines + column row; nothing capped at 100

    bad = client.get("/api/v1/business/reports/daily", params={"period": "custom", "start": "2026-02-10", "end": "2026-02-01"},
                     headers=owner)
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "INVALID_PERIOD"


def test_close_day_records_expected_and_counted_cash_without_locking(client):
    headers, services = setup_laundry(client)
    order = counter_order(client, headers, services, [("Shirt", 4)])
    client.post(f"/api/v1/business/orders/{order['id']}/payments", json={"method": "CASH"}, headers=headers)
    today = datetime.now(LOCAL_TZ).date()
    view = client.get("/api/v1/business/reports/daily", headers=headers).json()["day_close"]
    assert view["expected_cash"] == 8000 and view["closed"] is None

    closed = client.post("/api/v1/business/day-close", json={"date": today.isoformat(), "counted_cash": 7500,
                         "note": "500 short, float"}, headers=headers)
    assert closed.status_code == 201 and closed.json()["closed"]["variance"] == -500
    assert client.post("/api/v1/business/day-close", json={"date": today.isoformat()}, headers=headers).status_code == 409
    future = (today + timedelta(days=2)).isoformat()
    assert client.post("/api/v1/business/day-close", json={"date": future}, headers=headers).status_code == 422
    # Nothing is locked: a later payment still records and shows in the day's collections.
    second = counter_order(client, headers, services, [("Shirt", 1)])
    assert client.post(f"/api/v1/business/orders/{second['id']}/payments", json={"method": "CASH"}, headers=headers).status_code == 200
    assert client.get("/api/v1/business/reports/daily", headers=headers).json()["payments"]["CASH"]["amount"] == 10000


def test_manual_mobile_money_reference_is_unique_and_timestamps_are_kept(client):
    headers, services = setup_laundry(client)
    a = counter_order(client, headers, services, [("Shirt", 1)])
    b = counter_order(client, headers, services, [("Shirt", 1)])
    ref = f"QK{uuid.uuid4().hex[:8].upper()}"
    paid = client.post(f"/api/v1/business/orders/{a['id']}/payments", json={"method": "MOBILE_MONEY", "reference": ref},
                       headers=headers)
    assert paid.json()["status"] == "PAID" and paid.json()["reference"] == ref
    dup = client.post(f"/api/v1/business/orders/{b['id']}/payments", json={"method": "MOBILE_MONEY", "reference": ref},
                      headers=headers)
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "DUPLICATE_REFERENCE"
    with SessionLocal() as db:
        payment = db.query(Payment).filter(Payment.order_id == a["id"], Payment.status == "PAID").one()
        assert payment.paid_at is not None and payment.provider == "manual"
    listing = client.get("/api/v1/business/payments", params={"period": "today"}, headers=headers).json()
    assert listing["total"] == 1 and listing["summary"]["by_method"]["MOBILE_MONEY"]["amount"] == 2000
