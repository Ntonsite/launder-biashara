from datetime import datetime

from app.domain.clock import LOCAL_TZ
from app.models import BusinessHours
from app.services.marketplace import is_open

from .conftest import FRESHWASH, MIKOCHENI, services_by_name


def names(r):
    return [x["name"] for x in r.json()["items"]]


def test_nearby_is_sorted_by_distance_and_freshwash_is_closest_to_mikocheni(client):
    r = client.get("/api/v1/marketplace/laundries", params=MIKOCHENI)
    items = r.json()["items"]
    assert items[0]["slug"] == FRESHWASH
    distances = [x["distance_km"] for x in items]
    assert distances == sorted(distances)
    assert items[0]["cover_image_url"].startswith("/media/laundries/")


def test_radius_limits_results(client):
    near = client.get("/api/v1/marketplace/laundries", params={**MIKOCHENI, "radius_km": 1}).json()
    assert [x["slug"] for x in near["items"]] == [FRESHWASH]


def test_pending_marketplace_business_is_never_public(client):
    assert "T-Laundry" not in names(client.get("/api/v1/marketplace/laundries", params={"page_size": 50}))
    r = client.get("/api/v1/marketplace/laundries/t-laundry-mikocheni")
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"


def test_filters(client):
    pickup = client.get("/api/v1/marketplace/laundries", params={**MIKOCHENI, "pickup": True}).json()["items"]
    assert pickup and all(x["pickup_available"] for x in pickup)
    assert "CleanPro" not in [x["name"] for x in pickup]  # CleanPro has no pickup
    dry = names(client.get("/api/v1/marketplace/laundries", params={"service": "Dry Cleaning"}))
    assert "Safi Laundry" not in dry and "CleanPro" in dry
    assert names(client.get("/api/v1/marketplace/laundries", params={"q": "sinza"})) == ["Safi Laundry"]
    top = client.get("/api/v1/marketplace/laundries", params={"min_rating": 4.9}).json()["items"]
    assert all(x["rating"] >= 4.9 for x in top)


def test_browsing_works_without_location_and_sorts_by_rating(client):
    items = client.get("/api/v1/marketplace/laundries").json()["items"]
    assert all(x["distance_km"] is None for x in items)
    ratings = [x["rating"] for x in items]
    assert ratings == sorted(ratings, reverse=True)


def test_storefront_groups_services_and_reports_distance(client):
    store = client.get(f"/api/v1/marketplace/laundries/{FRESHWASH}", params=MIKOCHENI).json()
    groups = {g["category"]: g["services"] for g in store["service_groups"]}
    shirt = next(s for s in groups["Wash & Iron"] if s["name"] == "Shirt")
    assert shirt["price"] == 2000
    assert groups["Wash & Fold"][0]["pricing_model"] == "PER_KG" and groups["Wash & Fold"][0]["price"] == 4000
    assert store["distance_km"] < 1 and len(store["hours"]) == 7 and store["pickup_fee"] == 2000


def test_quote_is_priced_on_the_server(client):
    services = client.get(f"/api/v1/marketplace/laundries/{FRESHWASH}").json()["service_groups"]
    by_name = {s["name"]: s for g in services for s in g["services"]}
    body = {"items": [{"service_id": by_name["Shirt"]["id"], "quantity": 5}, {"service_id": by_name["Trouser"]["id"], "quantity": 2},
                      {"service_id": by_name["Wash & Fold"]["id"], "quantity": 2.5}], "fulfillment": "PICKUP"}
    q = client.post(f"/api/v1/marketplace/laundries/{FRESHWASH}/quote", json=body).json()
    assert q["subtotal"] == 5 * 2000 + 2 * 3000 + 10000 and q["delivery_fee"] == 2000 and q["total"] == q["subtotal"] + 2000


def test_quote_rejects_fractional_items_and_odd_kg(client):
    menu = services_by_name(client)
    url = f"/api/v1/marketplace/laundries/{FRESHWASH}/quote"
    bad_item = client.post(url, json={"items": [{"service_id": menu["Shirt"]["id"], "quantity": 1.5}]})
    bad_kg = client.post(url, json={"items": [{"service_id": menu["Wash & Fold"]["id"], "quantity": 1.3}]})
    assert bad_item.status_code == 422 and bad_kg.status_code == 422


def test_pickup_slots_respect_opening_hours(client):
    slots = client.get(f"/api/v1/marketplace/laundries/{FRESHWASH}/pickup-slots", params={"days": 3}).json()["slots"]
    for slot in slots:
        start = datetime.fromisoformat(slot["start"]).astimezone(LOCAL_TZ)
        assert start.strftime("%H:%M") >= ("09:00" if start.weekday() == 6 else "07:30")


def test_is_open_uses_local_hours():
    hours = [BusinessHours(weekday=0, opens_at="08:00", closes_at="18:00", closed=False)]
    assert is_open(hours, datetime(2026, 10, 5, 9, 0, tzinfo=LOCAL_TZ))       # Monday 09:00
    assert not is_open(hours, datetime(2026, 10, 5, 18, 0, tzinfo=LOCAL_TZ))   # closing time is exclusive
    assert not is_open(hours, datetime(2026, 10, 6, 9, 0, tzinfo=LOCAL_TZ))    # Tuesday not configured


def test_areas_support_manual_location(client):
    areas = {a["name"] for a in client.get("/api/v1/marketplace/areas").json()["items"]}
    assert {"Mikocheni", "Masaki", "Sinza"} <= areas
