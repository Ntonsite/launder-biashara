from pydantic import BaseModel, Field


class MarketplaceDecision(BaseModel):
    reason: str | None = Field(default=None, max_length=500)
    commission_rate: float | None = Field(default=None, ge=0, le=30)
