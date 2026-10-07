"""Walk-in customers at the counter: guest or named, any pricing model, full/part/no payment, straight into the
workflow, collected at the counter, and counted everywhere orders are counted — without Marketplace commission."""
import re
import uuid

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Commission, Order

from .test_business_admin import register


def laundry(client):
    headers, _ = register(client)
    ids = {}
    for body in ({"name": "Shirt", "price": 2000}, {"name": "Wash & Fold", "price": 4000, "pricing_model": "PER_KG"},
                 {"name": "Family bag (up to 6 kg)", "price": 15000, "pricing_model": "PACKAGE", "turnaround_hours": 48}):
        r = client.post("/api/v1/business/services", json=body, headers=headers)
        assert r.status_code == 201, r.text
        ids[body["name"]] = r.json()["id"]
    return headers, ids


def walk_in(client, headers, items, **extra):
    r = client.post("/api/v1/business/orders", json={"items": items, **extra}, headers=headers)
    assert r.status_code == 201, r.text
    return client.get(f"/api/v1/business/orders/{r.json()['id']}", headers=headers).json()


def move(client, headers, order_id, *steps):
    for step in steps:
        r = client.post(f"/api/v1/business/orders/{order_id}/status", json={"status": step}, headers=headers)
        assert r.status_code == 200, r.text


def test_guest_walk_in_paid_on_collection_runs_the_whole_workflow(client):
    headers, ids = laundry(client)
    order = walk_in(client, headers, [{"service_id": ids["Shirt"], "quantity": 3},
                                      {"service_id": ids["Wash & Fold"], "quantity": 2.5},
                                      {"service_id": ids["Family bag (up to 6 kg)"], "quantity": 1}],
                    customer_name="Mama Asha", notes="No starch")
    # 3 × 2,000 + 2.5 kg × 4,000 + 1 × 15,000 package
    assert order["total"] == 6000 + 10000 + 15000
    assert re.fullmatch(r"LN-[A-Z0-9]{6}", order["order_number"])
    assert order["source"] == "WALK_IN" and order["status"] == "RECEIVED"
    assert order["customer"]["is_guest"] and order["customer"]["name"] == "Mama Asha" and order["customer"]["phone"] is None
    assert order["payment_status"] == "PENDING" and order["balance"] == 31000

    # Guests are not CRM customers, but their orders are real orders.
    assert client.get("/api/v1/business/customers", headers=headers).json()["total"] == 0
    found = client.get("/api/v1/business/orders", params={"q": "Mama Asha"}, headers=headers).json()["items"]
    assert [o["id"] for o in found] == [order["id"]]

    move(client, headers, order["id"], "WASHING", "DRYING", "IRONING", "QUALITY_CHECK", "READY")
    unpaid = client.post(f"/api/v1/business/orders/{order['id']}/collect", json={}, headers=headers)
    assert unpaid.status_code == 409 and unpaid.json()["error"]["code"] == "PAYMENT_REQUIRED"
    done = client.post(f"/api/v1/business/orders/{order['id']}/collect", json={"payment": {"method": "CASH"}}, headers=headers)
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "COMPLETED" and done.json()["payment_status"] == "PAID"
    assert [e["status"] for e in done.json()["events"]][-3:] == ["READY", "DELIVERED", "COMPLETED"]

    with SessionLocal() as db:
        assert db.scalar(select(Commission).where(Commission.order_id == order["id"])) is None

    report = client.get("/api/v1/business/reports/daily", headers=headers).json()
    walk_ins = next(s for s in report["sources"] if s["source"] == "WALK_IN")
    assert walk_ins["orders"] == 1 and walk_ins["sales"] == 31000
    assert report["payments"]["CASH"]["amount"] == 31000 and report["money"]["collected"] == 31000
    assert report["marketplace"]["orders"] == 0 and report["marketplace"]["commission_accrued"] == 0
    assert report["customers"]["unique"] == 0  # the guest is not counted as a customer
    assert report["operations"]["completed"] == 1


def test_part_payment_leaves_a_balance_that_is_owed_and_collected_later(client):
    headers, ids = laundry(client)
    phone = "0754" + str(uuid.uuid4().int)[:6]
    order = walk_in(client, headers, [{"service_id": ids["Shirt"], "quantity": 6}], customer_name="Juma Ally", phone=phone,
                    payment={"method": "MOBILE_MONEY", "amount": 5000, "reference": f"QK{uuid.uuid4().hex[:8].upper()}"})
    assert order["payment_status"] == "PARTIAL" and order["amount_paid"] == 5000 and order["balance"] == 7000
    assert [p["amount"] for p in order["payments"]] == [5000]

    dash = client.get("/api/v1/business/dashboard", headers=headers).json()
    assert dash["today"]["outstanding"] == {"count": 1, "amount": 7000}
    assert dash["today"]["sales"]["value"] == 12000 and dash["today"]["collected"] == 5000

    too_much = client.post(f"/api/v1/business/orders/{order['id']}/payments", json={"method": "CASH", "amount": 9000},
                           headers=headers)
    assert too_much.status_code == 422 and too_much.json()["error"]["details"]["balance"] == 7000
    move(client, headers, order["id"], "IRONING", "READY")
    done = client.post(f"/api/v1/business/orders/{order['id']}/collect", json={"payment": {"method": "CASH"}}, headers=headers)
    assert done.json()["status"] == "COMPLETED" and done.json()["balance"] == 0
    assert sorted((p["method"], p["amount"]) for p in done.json()["payments"]) == [("CASH", 7000), ("MOBILE_MONEY", 5000)]

    report = client.get("/api/v1/business/reports/daily", headers=headers).json()
    assert report["payments"]["CASH"]["amount"] == 7000 and report["payments"]["MOBILE_MONEY"]["amount"] == 5000
    assert report["money"]["outstanding_now"]["amount"] == 0

    # The named walk-in customer has a history the laundry can see.
    customer = client.get("/api/v1/business/customers", params={"q": phone[-6:]}, headers=headers).json()["items"][0]
    assert customer["name"] == "Juma Ally" and customer["orders"] == 1 and customer["spend"] == 12000


def test_paid_in_full_at_drop_off_and_existing_customer_reuse(client):
    headers, ids = laundry(client)
    added = client.post("/api/v1/business/customers", json={"name": "Neema Said", "phone": "0713" + str(uuid.uuid4().int)[:6]},
                        headers=headers).json()
    order = walk_in(client, headers, [{"service_id": ids["Family bag (up to 6 kg)"], "quantity": 2}],
                    customer_id=added["id"], payment={"method": "CASH"})
    assert order["customer"]["id"] == added["id"] and order["payment_status"] == "PAID" and order["total"] == 30000
    again = client.post(f"/api/v1/business/orders/{order['id']}/payments", json={"method": "CASH"}, headers=headers)
    assert again.status_code == 409 and again.json()["error"]["code"] == "ALREADY_PAID"

    bad = client.post("/api/v1/business/orders", json={"items": [{"service_id": ids["Family bag (up to 6 kg)"], "quantity": 1.5}]},
                      headers=headers)
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "INVALID_QUANTITY"
    phone_order = client.post("/api/v1/business/orders", json={"source": "PHONE", "items": [{"service_id": ids["Shirt"], "quantity": 1}]},
                              headers=headers)
    assert phone_order.status_code == 422 and phone_order.json()["error"]["code"] == "PHONE_REQUIRED"
    # Another laundry cannot attach orders to this laundry's customer.
    other, other_ids = laundry(client)
    stolen = client.post("/api/v1/business/orders", headers=other,
                         json={"customer_id": added["id"], "items": [{"service_id": other_ids["Shirt"], "quantity": 1}]})
    assert stolen.status_code == 404


def test_guest_record_is_shared_per_laundry(client):
    headers, ids = laundry(client)
    a = walk_in(client, headers, [{"service_id": ids["Shirt"], "quantity": 1}])
    b = walk_in(client, headers, [{"service_id": ids["Shirt"], "quantity": 1}])
    assert a["customer"]["id"] == b["customer"]["id"] and a["customer"]["name"] == "Walk-in customer"
    with SessionLocal() as db:
        assert db.get(Order, a["id"]).guest_name is None
