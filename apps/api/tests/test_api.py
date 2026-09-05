from fastapi.testclient import TestClient
from app.main import app
from uuid import uuid4

client=TestClient(app)
def login(email,password):return client.post("/api/v1/auth/login",json={"email":email,"password":password})
def test_health():assert client.get("/health").json()["status"]=="healthy"
def test_seeded_business_login():
    response=login("owner@t-laundry.co.tz","Demo123!");assert response.status_code==200;assert response.json()["user"]["role"]=="BUSINESS_OWNER"
def test_invalid_login_is_rejected():assert login("owner@t-laundry.co.tz","incorrect!").status_code==401
def test_business_cannot_access_admin():
    token=login("owner@t-laundry.co.tz","Demo123!").json()["access_token"];assert client.get("/api/v1/admin/dashboard",headers={"Authorization":f"Bearer {token}"}).status_code==403
def test_admin_can_read_dashboard():
    token=login("admin@launder.co.tz","Admin123!").json()["access_token"];response=client.get("/api/v1/admin/dashboard",headers={"Authorization":f"Bearer {token}"});assert response.status_code==200;assert "gmv" in response.json()
def test_new_business_gets_isolated_operational_workspace():
    suffix=uuid4().hex[:8];response=client.post("/api/v1/auth/business/register",json={"full_name":"New Owner","business_name":f"Laundry {suffix}","phone":"+255700000009","email":f"owner-{suffix}@example.co.tz","password":"Secure123!"});assert response.status_code==201
    headers={"Authorization":f"Bearer {response.json()['access_token']}"}
    assert client.put("/api/v1/business/onboarding",headers=headers,json={"step":1,"data":{"business_name":f"Laundry {suffix}"},"completed":False}).status_code==200
    assert client.post("/api/v1/business/services",headers=headers,json={"name":"Shirt","price":2000,"pricing_model":"PER_ITEM","turnaround_hours":24}).status_code==201
    assert client.post("/api/v1/business/orders",headers=headers,json={"customer_name":"New Customer","phone":"+255711000009","source":"WALK_IN","total":12000}).status_code==201
    orders=client.get("/api/v1/business/orders",headers=headers).json();assert orders["total"]==1
