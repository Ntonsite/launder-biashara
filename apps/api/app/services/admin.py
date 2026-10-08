from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from ..core.errors import AppError
from ..models import Business, MarketplaceAccount, User
from .audit import audit

# decision → (allowed current states, resulting state, reason required)
DECISIONS = {
    "approve": ({"PENDING_REVIEW"}, "ACTIVE", False),
    "reject": ({"PENDING_REVIEW"}, "REJECTED", True),
    "suspend": ({"ACTIVE"}, "SUSPENDED", True),
    "reinstate": ({"SUSPENDED"}, "ACTIVE", False),
}


class MarketplaceAdminService:
    def __init__(self, db: Session):
        self.db = db

    def decide(self, account: MarketplaceAccount, decision: str, actor: User, reason: str | None,
               commission_rate: float | None = None) -> MarketplaceAccount:
        if decision not in DECISIONS:
            raise AppError(422, "INVALID_DECISION", "Unknown decision")
        allowed, target, needs_reason = DECISIONS[decision]
        if account.status not in allowed:
            raise AppError(409, "INVALID_TRANSITION", f"Cannot {decision} an application that is {account.status}")
        if needs_reason and not (reason and reason.strip()):
            raise AppError(422, "REASON_REQUIRED", "A reason is required for this decision")
        if decision in ("approve", "reinstate"):
            from .entitlements import require_feature

            require_feature(self.db, account.business_id, "marketplace_eligible")  # before anything changes
        previous = account.status
        now = datetime.now(UTC)
        account.status = target
        account.reviewed_at, account.reviewed_by = now, actor.id
        account.rejection_reason = reason.strip() if needs_reason else None
        if decision == "approve":
            account.approved_at = now
            business = self.db.get(Business, account.business_id)
            business.verification_status = "VERIFIED"
            if business.status == "ONBOARDING":
                business.status = "ACTIVE"
        if commission_rate is not None:
            from .pricing import PricingAdmin  # commission terms are versioned rules, never a field edit

            PricingAdmin(self.db, actor).create_rule("BUSINESS", account.business_id, Decimal(str(commission_rate)), 0, False,
                                                     True, None, None, f"Set on {decision}")
        audit(self.db, actor.id, f"MARKETPLACE_{decision.upper()}", "marketplace_account", account.id,
              from_status=previous, to_status=target, reason=reason)
        self.db.commit()
        return account
