from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from .orders import CartItem

HM = r"^([01]\d|2[0-3]):[0-5]\d$"


class OnboardingUpdate(BaseModel):
    step: int = Field(ge=1, le=9)
    data: dict[str, Any]
    completed: bool = False


class ServiceCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=500)
    category: str = Field(default="Wash & Iron", min_length=2, max_length=80)
    pricing_model: Literal["PER_ITEM", "PER_KG"] = "PER_ITEM"
    price: int = Field(ge=0, le=10_000_000)
    turnaround_hours: int = Field(default=24, gt=0, le=720)
    sort_order: int = Field(default=0, ge=0, le=1000)
    active: bool = True


class CustomerCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=9, max_length=20)
    email: str | None = None


class BusinessOrderCreate(BaseModel):
    customer_name: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=9, max_length=20)
    source: Literal["WALK_IN", "PHONE", "WHATSAPP"] = "WALK_IN"
    fulfillment: Literal["PICKUP", "DROP_OFF"] = "DROP_OFF"
    items: list[CartItem] = Field(default_factory=list, max_length=50)
    # Quick-entry amount for counter orders without itemisation; ignored when items are provided.
    total: int | None = Field(default=None, gt=0, le=100_000_000)
    payment_method: Literal["CASH", "MOBILE_MONEY"] = "CASH"
    notes: str = Field(default="", max_length=500)


class BusinessProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    phone: str | None = Field(default=None, min_length=9, max_length=20)
    address: str | None = Field(default=None, min_length=3, max_length=255)
    area: str | None = Field(default=None, min_length=2, max_length=80)
    city: str | None = Field(default=None, min_length=2, max_length=80)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    pickup_enabled: bool | None = None
    pickup_fee: int | None = Field(default=None, ge=0, le=100_000)


class DayHours(BaseModel):
    weekday: int = Field(ge=0, le=6)
    opens_at: str = Field(pattern=HM)
    closes_at: str = Field(pattern=HM)
    closed: bool = False

    @field_validator("closes_at")
    @classmethod
    def _after_open(cls, v, info):
        if "opens_at" in info.data and v <= info.data["opens_at"]:
            raise ValueError("Closing time must be after opening time")
        return v


class HoursUpdate(BaseModel):
    days: list[DayHours] = Field(min_length=1, max_length=7)


class StaffCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=8, max_length=128)
    role: Literal["BRANCH_MANAGER", "STAFF"] = "STAFF"


class MarketplaceApplication(BaseModel):
    contact_name: str = Field(min_length=2, max_length=120)
    registration_number: str = Field(default="", max_length=60)
    tin: str = Field(default="", max_length=30)
    pickup_radius_km: float = Field(default=8, ge=1, le=30)
    accept_terms: bool

    @field_validator("accept_terms")
    @classmethod
    def _must_accept(cls, v):
        if not v:
            raise ValueError("Marketplace terms must be accepted")
        return v
