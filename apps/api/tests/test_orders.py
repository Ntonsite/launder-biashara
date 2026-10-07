import json
import uuid

import pytest

from app.domain import order_states as S
from app.services.payments import sign

from .conftest import FRESHWASH, bearer, customer_login, first_slot, services_by_name, staff_login
from .test_auth import new_phone

MIKOCHENI_ADDRESS = {"line": "Plot 12, Old Bagamoyo Rd", "area": "Mikocheni", "notes": "Blue gate",
                     "latitude": -6.7690, "longitude": 39.2470}


def place(client, headers, items, key=None, **overrides):
    body = {"laundry_slug": FRESHWASH, "items": items, "fulfillment": "PICKUP", "address": MIKOCHENI_ADDRESS,
            "pickup_window_start": first_slot(client), "payment_method": "CASH", **overrides}
    return client.post("/api/v1/customer/orders", json=body, headers={**headers, "Idempotency-Key": key or uuid.uuid4().hex})


@pytest.fixture
def customer(client):
    return bearer(customer_login(client, new_phone(), name="Neema Mushi")["access_token"])


def shirts_and_trousers(client):
    menu = services_by_name(client)
    return [{"service_id": menu["Shirt"]["id"], "quantity": 5}, {"service_id": menu["Trouser"]["id"], "quantity": 2}]


def advance(client, owner, order_id, *statuses):
    for status in statuses:
        r = client.post(f"/api/v1/business/orders/{order_id}/status", json={"status": status}, headers=owner)
        assert r.status_code == 200, (status, r.text)
    return r.json()


def test_full_marketplace_journey(client, customer, owner):
    # Customer places 5 shirts + 2 trousers for pickup.
    r = place(client, customer, shirts_and_trousers(client), key="journey-key-1", expected_total=18000)
    assert r.status_code == 201, r.text
    order = r.json()
    assert order["order_number"].startswith("LN-") and order["status"] == S.NEW
    assert (order["subtotal"], order["delivery_fee"], order["total"]) == (16000, 2000, 18000)
    assert order["pickup_address"].startswith("Plot 12") and order["payment"]["status"] == "PENDING"

    # Double-tap protection: the same Idempotency-Key returns the same order instead of a duplicate.
    again = place(client, customer, shirts_and_trousers(client), key="journey-key-1")
    assert again.status_code == 200 and again.json()["id"] == order["id"]

    # FreshWash receives the same order.
    listing = client.get("/api/v1/business/orders", params={"q": order["order_number"]}, headers=owner).json()
    assert listing["total"] == 1 and listing["items"][0]["source"] == "MARKETPLACE"
    detail = client.get(f"/api/v1/business/orders/{order['id']}", headers=owner).json()
    assert detail["allowed_next"] == [S.ACCEPTED, S.CANCELLED, S.REJECTED]

    # Arbitrary jumps are refused.
    bad = client.post(f"/api/v1/business/orders/{order['id']}/status", json={"status": "READY"}, headers=owner)
    assert bad.status_code == 409 and bad.json()["error"]["code"] == "INVALID_TRANSITION"

    advance(client, owner, order["id"], S.ACCEPTED, S.AWAITING_PICKUP, S.RECEIVED, S.WASHING, S.IRONING, S.QUALITY_CHECK,
            S.READY, S.OUT_FOR_DELIVERY, S.DELIVERED)

    # Completion requires payment; cash is recorded by the laundry.
    blocked = client.post(f"/api/v1/business/orders/{order['id']}/status", json={"status": "COMPLETED"}, headers=owner)
    assert blocked.json()["error"]["code"] == "PAYMENT_REQUIRED"
    assert client.post(f"/api/v1/business/orders/{order['id']}/payments/cash", headers=owner).json()["status"] == "PAID"

    # Customer sees the same progression and confirms completion.
    tracked = client.get(f"/api/v1/customer/orders/{order['id']}", headers=customer).json()
    assert tracked["status"] == S.DELIVERED and tracked["can_confirm"] and tracked["can_review"]
    assert [e["status"] for e in tracked["events"]] == [S.NEW, S.ACCEPTED, S.AWAITING_PICKUP, S.RECEIVED, S.WASHING, S.IRONING,
                                                       S.QUALITY_CHECK, S.READY, S.OUT_FOR_DELIVERY, S.DELIVERED]
    done = client.post(f"/api/v1/customer/orders/{order['id']}/confirm", headers=customer).json()
    assert done["status"] == S.COMPLETED

    # Commission: 5% of laundry services (16,000), not of the pickup fee.
    analytics = client.get("/api/v1/business/analytics", headers=owner).json()
    assert analytics["marketplace_commission"] >= 800

    # Review updates the public rating.
    before = client.get(f"/api/v1/marketplace/laundries/{FRESHWASH}").json()
    assert client.post(f"/api/v1/customer/orders/{order['id']}/review", json={"rating": 5, "comment": "Safi sana!"},
                       headers=customer).status_code == 201
    after = client.get(f"/api/v1/marketplace/laundries/{FRESHWASH}").json()
    assert after["review_count"] == before["review_count"] + 1
    assert after["reviews"][0]["comment"] == "Safi sana!" and after["reviews"][0]["author"] == "Neema M."
    assert client.post(f"/api/v1/customer/orders/{order['id']}/review", json={"rating": 1}, headers=customer).status_code == 409

    # Notifications were recorded for meaningful states; push is honestly NOT_CONFIGURED.
    kinds = {n["kind"] for n in client.get("/api/v1/customer/notifications", headers=customer).json()["items"]}
    assert {"ORDER_ACCEPTED", "PICKUP_SCHEDULED", "ORDER_READY", "ORDER_DELIVERED", "PAYMENT_PAID"} <= kinds

    # Order again: the laundry raises the shirt price; reorder uses the new price and says so.
    menu = services_by_name(client)
    shirt = menu["Shirt"]
    client.put(f"/api/v1/business/services/{shirt['id']}", json={**{k: shirt[k] for k in ("name", "description", "category",
               "pricing_model", "turnaround_hours", "sort_order", "active")}, "price": 2500}, headers=owner)
    try:
        again = client.get(f"/api/v1/customer/orders/{order['id']}/reorder", headers=customer).json()
        assert again["quote"]["subtotal"] == 5 * 2500 + 2 * 3000
        assert {"type": "PRICE_CHANGED", "name": "Shirt", "old_price": 2000, "new_price": 2500} in again["changes"]
        # A stale client total is refused rather than silently charged.
        stale = place(client, customer, shirts_and_trousers(client), expected_total=18000)
        assert stale.status_code == 409 and stale.json()["error"]["code"] == "PRICE_CHANGED"
    finally:
        client.put(f"/api/v1/business/services/{shirt['id']}", json={**{k: shirt[k] for k in ("name", "description", "category",
                   "pricing_model", "turnaround_hours", "sort_order", "active")}, "price": 2000}, headers=owner)

    # Order history groups.
    completed = client.get("/api/v1/customer/orders", params={"group": "completed"}, headers=customer).json()
    assert completed["items"][0]["id"] == order["id"]


def test_orders_are_private_to_their_owner(client, customer, owner):
    order = place(client, customer, shirts_and_trousers(client)).json()
    stranger = bearer(customer_login(client, new_phone())["access_token"])
    assert client.get(f"/api/v1/customer/orders/{order['id']}", headers=stranger).status_code == 404
    other_business = bearer(staff_login(client, "owner@cleanpro.co.tz")["access_token"])
    assert client.get(f"/api/v1/business/orders/{order['id']}", headers=other_business).status_code == 404
    assert client.post(f"/api/v1/business/orders/{order['id']}/status", json={"status": "ACCEPTED"},
                       headers=other_business).status_code == 404


def test_customer_can_cancel_only_before_acceptance(client, customer, owner):
    first = place(client, customer, shirts_and_trousers(client)).json()
    assert client.post(f"/api/v1/customer/orders/{first['id']}/cancel", json={}, headers=customer).json()["status"] == S.CANCELLED
    second = place(client, customer, shirts_and_trousers(client)).json()
    advance(client, owner, second["id"], S.ACCEPTED)
    assert client.post(f"/api/v1/customer/orders/{second['id']}/cancel", json={}, headers=customer).status_code == 409


def test_rejection_requires_reason_and_reaches_customer(client, customer, owner):
    order = place(client, customer, shirts_and_trousers(client)).json()
    no_reason = client.post(f"/api/v1/business/orders/{order['id']}/status", json={"status": "REJECTED"}, headers=owner)
    assert no_reason.status_code == 422
    client.post(f"/api/v1/business/orders/{order['id']}/status", json={"status": "REJECTED", "note": "Fully booked today"}, headers=owner)
    seen = client.get(f"/api/v1/customer/orders/{order['id']}", headers=customer).json()
    assert seen["status"] == S.REJECTED and seen["cancel_reason"] == "Fully booked today"


def test_drop_off_order_skips_pickup_and_delivery_legs(client, customer, owner):
    r = place(client, customer, shirts_and_trousers(client), fulfillment="DROP_OFF", address=None, pickup_window_start=None)
    assert r.status_code == 201 and r.json()["delivery_fee"] == 0
    order = r.json()
    assert S.AWAITING_PICKUP not in order["stages"] and S.OUT_FOR_DELIVERY not in order["stages"]
    detail = advance(client, owner, order["id"], S.ACCEPTED)
    assert S.AWAITING_PICKUP not in detail["allowed_next"]
    detail = advance(client, owner, order["id"], S.RECEIVED, S.IRONING, S.READY)
    assert detail["allowed_next"] == [S.DELIVERED]


def test_pickup_validation(client, customer):
    items = shirts_and_trousers(client)
    far = place(client, customer, items, address={**MIKOCHENI_ADDRESS, "latitude": -6.85, "longitude": 39.31})
    assert far.json()["error"]["code"] == "OUTSIDE_PICKUP_AREA"
    bad_slot = place(client, customer, items, pickup_window_start="2020-01-01T08:00:00+03:00")
    assert bad_slot.json()["error"]["code"] == "PICKUP_SLOT_UNAVAILABLE"
    no_pickup = place(client, customer, items, laundry_slug="cleanpro-masaki")
    assert no_pickup.status_code == 409


def test_order_requires_idempotency_key_and_name(client):
    nameless = bearer(customer_login(client, new_phone(), name=None)["access_token"])
    items = shirts_and_trousers(client)
    body = {"laundry_slug": FRESHWASH, "items": items, "fulfillment": "DROP_OFF", "payment_method": "CASH"}
    assert client.post("/api/v1/customer/orders", json=body, headers=nameless).status_code == 422
    r = client.post("/api/v1/customer/orders", json=body, headers={**nameless, "Idempotency-Key": uuid.uuid4().hex})
    assert r.json()["error"]["code"] == "PROFILE_INCOMPLETE"


def test_mobile_money_sandbox_flow(client, customer):
    order = place(client, customer, shirts_and_trousers(client), payment_method="MOBILE_MONEY").json()
    assert order["can_pay"]
    payment = client.post(f"/api/v1/customer/orders/{order['id']}/payments/mobile-money", json={"phone": "0712000111"},
                          headers=customer).json()
    assert payment["status"] == "PROCESSING" and payment["reference"].startswith("SBX-")
    body = json.dumps({"reference": payment["reference"], "status": "PAID"}).encode()
    assert client.post("/api/v1/payments/webhooks/sandbox", content=body, headers={"X-Launder-Signature": "forged"}).status_code == 401
    ok = client.post("/api/v1/payments/webhooks/sandbox", content=body, headers={"X-Launder-Signature": sign(body)})
    assert ok.json()["status"] == "PAID"
    # Providers retry callbacks; a duplicate is harmless.
    retry = client.post("/api/v1/payments/webhooks/sandbox", content=body, headers={"X-Launder-Signature": sign(body)})
    assert retry.json()["status"] == "PAID"
    assert client.get(f"/api/v1/customer/orders/{order['id']}", headers=customer).json()["payment_status"] == "PAID"


def test_failed_mobile_money_can_be_retried(client, customer):
    order = place(client, customer, shirts_and_trousers(client), payment_method="MOBILE_MONEY").json()
    url = f"/api/v1/customer/orders/{order['id']}/payments/mobile-money"
    first = client.post(url, json={"phone": "0712000111"}, headers=customer).json()
    client.post(f"/api/v1/dev/payments/{first['reference']}/simulate", json={"outcome": "FAILED", "reason": "Insufficient balance"})
    seen = client.get(f"/api/v1/customer/orders/{order['id']}", headers=customer).json()
    assert seen["payment"]["status"] == "FAILED" and seen["can_pay"]
    retry = client.post(url, json={"phone": "0712000111"}, headers=customer).json()
    assert retry["status"] == "PROCESSING"


def test_counter_order_is_priced_from_services(client, owner):
    menu = services_by_name(client)
    r = client.post("/api/v1/business/orders", json={"customer_name": "Walk In", "phone": "0754000222",
                    "items": [{"service_id": menu["Suit (2 piece)"]["id"], "quantity": 1}]}, headers=owner)
    assert r.status_code == 201 and r.json()["total"] == 8000 and r.json()["status"] == S.ACCEPTED


def test_state_machine_rules():
    assert S.allowed_next(S.READY, "PICKUP") == [S.OUT_FOR_DELIVERY]
    assert S.allowed_next(S.READY, "DROP_OFF") == [S.DELIVERED]
    assert not S.can_transition(S.WASHING, S.RECEIVED, "PICKUP")  # never backwards
    assert S.can_transition(S.RECEIVED, S.IRONING, "DROP_OFF")      # iron-only orders skip washing
    assert S.allowed_next(S.COMPLETED, "PICKUP") == []
