from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class CartItem(BaseModel):
    service_id: str = Field(min_length=1, max_length=36)
    quantity: Decimal = Field(gt=0, le=200, max_digits=6, decimal_places=2)


class QuoteRequest(BaseModel):
    items: list[CartItem] = Field(min_length=1, max_length=50)
    fulfillment: Literal["PICKUP", "DROP_OFF"] = "DROP_OFF"


class AddressInput(BaseModel):
    line: str = Field(min_length=3, max_length=255)
    area: str = Field(default="", max_length=80)
    notes: str = Field(default="", max_length=255)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


class CustomerOrderCreate(BaseModel):
    laundry_slug: str = Field(min_length=1, max_length=180)
    items: list[CartItem] = Field(min_length=1, max_length=50)
    fulfillment: Literal["PICKUP", "DROP_OFF"]
    address_id: str | None = None
    address: AddressInput | None = None
    pickup_window_start: datetime | None = None
    payment_method: Literal["CASH", "MOBILE_MONEY"]
    notes: str = Field(default="", max_length=500)
    # When supplied, the order is refused with PRICE_CHANGED if the server-side total differs.
    expected_total: int | None = Field(default=None, ge=0)


class CancelRequest(BaseModel):
    reason: str = Field(default="", max_length=255)


class ReviewCreate(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str = Field(default="", max_length=1000)


class MobileMoneyPayment(BaseModel):
    phone: str = Field(min_length=9, max_length=20)


class StatusChange(BaseModel):
    status: str = Field(min_length=3, max_length=20)
    note: str = Field(default="", max_length=255)


class AddressCreate(AddressInput):
    label: str = Field(default="Home", min_length=1, max_length=40)
    is_default: bool = False


class DeviceRegistration(BaseModel):
    token: str = Field(min_length=10, max_length=512)
    platform: Literal["android", "ios", "web"]


class SandboxPaymentOutcome(BaseModel):
    outcome: Literal["PAID", "FAILED"]
    reason: str = Field(default="", max_length=255)
