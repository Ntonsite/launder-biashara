from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class MarketplaceDecision(BaseModel):
    reason: str | None = Field(default=None, max_length=500)
    commission_rate: float | None = Field(default=None, ge=0, le=30)
    # Approval only: individual trial terms instead of the default policy, or no trial at all (finance roles).
    trial_days: int | None = Field(default=None, ge=1, le=365)
    trial_rate: Decimal | None = Field(default=None, ge=0, le=50, decimal_places=2)
    skip_trial: bool = False


class MarketplaceInvite(BaseModel):
    note: str = Field(default="", max_length=500)
    trial_days: int | None = Field(default=None, ge=1, le=365)
    trial_rate: Decimal | None = Field(default=None, ge=0, le=50, decimal_places=2)
    launch_cohort: bool | None = None


class TrialGrant(BaseModel):
    days: int | None = Field(default=None, ge=1, le=365)
    rate: Decimal | None = Field(default=None, ge=0, le=50, decimal_places=2)
    reason: str = Field(min_length=3, max_length=255)


class TrialExtend(BaseModel):
    days: int = Field(ge=1, le=365)
    reason: str = Field(min_length=3, max_length=255)


class CohortSet(BaseModel):
    included: bool
    reason: str = Field(default="", max_length=255)


class MarketplaceSettingsUpdate(BaseModel):
    values: dict[str, Any] = Field(min_length=1)
    reason: str = Field(min_length=3, max_length=255)
