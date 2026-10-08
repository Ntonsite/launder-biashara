from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field

Reason = Field(min_length=3, max_length=255, description="Why — kept in the pricing audit log")


class PlanChange(BaseModel):
    plan_id: str = Field(max_length=36)
    interval: Literal["MONTHLY", "ANNUAL"] = "MONTHLY"


class PlanCreate(BaseModel):
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{1,39}$")
    name: str = Field(min_length=2, max_length=80)
    description: str = Field(default="", max_length=500)
    benefits: list[str] = Field(default_factory=list, max_length=20)
    status: Literal["ACTIVE", "HIDDEN"] = "ACTIVE"
    trial_days: int = Field(default=0, ge=0, le=365)
    grace_days: int = Field(default=7, ge=0, le=90)
    max_staff: int | None = Field(default=None, ge=0, le=10_000)
    max_branches: int | None = Field(default=None, ge=1, le=1000)
    sort_order: int = Field(default=10, ge=0, le=1000)
    monthly_price: int = Field(ge=0, le=100_000_000)
    annual_price: int = Field(ge=0, le=1_000_000_000)
    features: dict[str, bool] = Field(default_factory=dict)
    reason: str = Reason


class PlanUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    benefits: list[str] | None = Field(default=None, max_length=20)
    status: Literal["ACTIVE", "HIDDEN", "RETIRED"] | None = None
    is_default: bool | None = None
    trial_days: int | None = Field(default=None, ge=0, le=365)
    grace_days: int | None = Field(default=None, ge=0, le=90)
    max_staff: int | None = Field(default=None, ge=0, le=10_000)
    max_branches: int | None = Field(default=None, ge=1, le=1000)
    sort_order: int | None = Field(default=None, ge=0, le=1000)
    reason: str = Reason


class PriceSet(BaseModel):
    interval: Literal["MONTHLY", "ANNUAL"]
    amount: int = Field(ge=0, le=1_000_000_000)
    effective_from: datetime | None = None
    reason: str = Reason


class FeaturesSet(BaseModel):
    features: dict[str, bool]
    reason: str = Reason


class RuleCreate(BaseModel):
    scope: Literal["DEFAULT", "BUSINESS", "PROMOTION"]
    business_id: str | None = Field(default=None, max_length=36)
    rate: Decimal = Field(ge=0, le=50, max_digits=5, decimal_places=2)
    min_commission: int = Field(default=0, ge=0, le=1_000_000)
    include_pickup_fee: bool = False
    discounts_reduce_basis: bool = True
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    reason: str = Reason


class RuleEnd(BaseModel):
    at: datetime | None = None
    reason: str = Reason


class SettingSet(BaseModel):
    value: Any
    reason: str = Reason


class OverrideCreate(BaseModel):
    business_id: str = Field(max_length=36)
    type: Literal["COMPLIMENTARY_PLAN", "PLAN_PRICE", "PLAN_DISCOUNT"]
    plan_id: str = Field(max_length=36)
    value: Decimal = Field(default=Decimal("0"), ge=0, le=100_000_000)
    effective_from: datetime | None = None
    expires_at: datetime | None = None
    days: int | None = Field(default=None, ge=1, le=3650, description="Shortcut: expires this many days after start")
    reason: str = Reason


class ReasonOnly(BaseModel):
    reason: str = Reason


class PilotCreate(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    plan_id: str = Field(max_length=36)
    duration_days: int = Field(ge=7, le=365)
    transition_policy: Literal["DOWNGRADE", "INVOICE"] = "DOWNGRADE"
    notes: str = Field(default="", max_length=500)


class PilotEnroll(BaseModel):
    business_ids: list[str] = Field(min_length=1, max_length=200)
    starts_at: datetime | None = None


class AdminSubscriptionAssign(BaseModel):
    plan_id: str = Field(max_length=36)
    interval: Literal["MONTHLY", "ANNUAL"] = "MONTHLY"
    reason: str = Reason


class SubscriptionPaymentCreate(BaseModel):
    amount: int = Field(gt=0, le=1_000_000_000)
    method: Literal["CASH", "BANK_TRANSFER", "MOBILE_MONEY"]
    reference: str = Field(default="", max_length=80)
    received_at: datetime | None = None
    note: str = Field(default="", max_length=255)
