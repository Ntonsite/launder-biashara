import json
import re
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.errors import AppError
from ..core.security import hash_password
from ..domain.clock import now_utc
from ..domain.phone import normalize_tz_phone
from ..models import Business, BusinessHours, BusinessOnboarding, MarketplaceAccount, Service, User
from ..schemas.auth import BusinessRegisterRequest
from ..schemas.business import BusinessProfileUpdate, HoursUpdate, MarketplaceApplication, StaffCreate
from .audit import audit

DEFAULT_LAT, DEFAULT_LNG = -6.7924, 39.2083  # Dar es Salaam city centre, only until the owner sets a location


def unique_slug(db: Session, name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "laundry"
    slug, number = base, 2
    while db.scalar(select(Business.id).where(Business.slug == slug)):
        slug, number = f"{base}-{number}", number + 1
    return slug


class BusinessRegistrationService:
    def __init__(self, db: Session):
        self.db = db

    def register(self, payload: BusinessRegisterRequest) -> tuple[User, Business]:
        if self.db.scalar(select(User).where(User.email == payload.email.lower())):
            raise AppError(409, "EMAIL_TAKEN", "An account with this email already exists")
        try:
            phone = normalize_tz_phone(payload.phone)
        except ValueError as exc:
            raise AppError(422, "INVALID_PHONE", str(exc)) from exc
        user = User(email=payload.email.lower(), password_hash=hash_password(payload.password), full_name=payload.full_name,
                    role="BUSINESS_OWNER")
        self.db.add(user)
        self.db.flush()
        business = Business(owner_id=user.id, name=payload.business_name, slug=unique_slug(self.db, payload.business_name),
                            phone=phone, area="", status="ONBOARDING", verification_status="UNVERIFIED",
                            latitude=None, longitude=None, pickup_enabled=False)
        self.db.add(business)
        self.db.flush()
        # Marketplace participation is opt-in: every new business starts NOT_ENROLLED and is never listed automatically.
        self.db.add_all([BusinessOnboarding(business_id=business.id), MarketplaceAccount(business_id=business.id, status="NOT_ENROLLED")])
        audit(self.db, user.id, "BUSINESS_REGISTERED", "business", business.id)
        self.db.commit()
        return user, business

    def save_onboarding(self, business: Business, record: BusinessOnboarding, step: int, data: dict, completed: bool):
        stored = json.loads(record.data_json or "{}")
        stored[str(step)] = data
        record.data_json = json.dumps(stored)
        record.current_step = max(record.current_step, min(step + 1, 9))
        if completed:
            record.completed = True
            if business.status == "ONBOARDING":
                business.status = "ACTIVE"
        audit(self.db, business.owner_id, "ONBOARDING_UPDATED", "business", business.id, step=step)
        self.db.commit()
        return record


class BusinessProfileService:
    def __init__(self, db: Session):
        self.db = db

    def update_profile(self, business: Business, payload: BusinessProfileUpdate, actor: User) -> Business:
        values = payload.model_dump(exclude_unset=True)
        if "phone" in values and values["phone"]:
            try:
                values["phone"] = normalize_tz_phone(values["phone"])
            except ValueError as exc:
                raise AppError(422, "INVALID_PHONE", str(exc)) from exc
        if ("latitude" in values) != ("longitude" in values):
            raise AppError(422, "LOCATION_INCOMPLETE", "Latitude and longitude must be set together")
        for key, value in values.items():
            setattr(business, key, value)
        audit(self.db, actor.id, "BUSINESS_PROFILE_UPDATED", "business", business.id, fields=sorted(values))
        self.db.commit()
        return business

    def set_hours(self, business: Business, payload: HoursUpdate, actor: User) -> list[BusinessHours]:
        days = {d.weekday: d for d in payload.days}
        if len(days) != len(payload.days):
            raise AppError(422, "DUPLICATE_DAY", "Each weekday can appear only once")
        existing = {h.weekday: h for h in business.hours}
        for weekday, d in days.items():
            h = existing.get(weekday)
            if h is None:
                h = BusinessHours(weekday=weekday)
                business.hours.append(h)
            h.opens_at, h.closes_at, h.closed = d.opens_at, d.closes_at, d.closed
        audit(self.db, actor.id, "BUSINESS_HOURS_UPDATED", "business", business.id)
        self.db.commit()
        self.db.refresh(business)
        return business.hours

    def readiness(self, business: Business) -> list[dict]:
        """Checklist that must be complete before a business can apply to the marketplace."""
        active_services = self.db.scalar(select(func.count(Service.id)).where(Service.business_id == business.id,
                                                                             Service.active.is_(True))) or 0
        return [
            {"key": "profile", "done": bool(business.name and business.phone and business.description)},
            {"key": "location", "done": bool(business.area and business.address and business.latitude is not None)},
            {"key": "services", "done": active_services > 0},
            {"key": "hours", "done": any(not h.closed for h in business.hours)},
        ]

    def apply_to_marketplace(self, business: Business, payload: MarketplaceApplication, actor: User) -> MarketplaceAccount:
        account = self.db.scalar(select(MarketplaceAccount).where(MarketplaceAccount.business_id == business.id))
        if account is None:
            account = MarketplaceAccount(business_id=business.id, status="NOT_ENROLLED")
            self.db.add(account)
        if account.status not in ("NOT_ENROLLED", "REJECTED"):
            raise AppError(409, "APPLICATION_EXISTS", f"Marketplace application is already {account.status}")
        missing = [c["key"] for c in self.readiness(business) if not c["done"]]
        if missing:
            raise AppError(409, "NOT_READY", "Complete your business setup before applying", {"missing": missing})
        account.status = "PENDING_REVIEW"
        account.contact_name = payload.contact_name
        account.registration_number = payload.registration_number or None
        account.tin = payload.tin or None
        account.pickup_radius_km = Decimal(str(payload.pickup_radius_km))
        account.submitted_at = now_utc()
        account.rejection_reason = None
        audit(self.db, actor.id, "MARKETPLACE_APPLIED", "marketplace_account", account.id or business.id)
        self.db.commit()
        return account

    def add_staff(self, business: Business, payload: StaffCreate, actor: User) -> User:
        if self.db.scalar(select(User).where(User.email == payload.email.lower())):
            raise AppError(409, "EMAIL_TAKEN", "An account with this email already exists")
        staff = User(email=payload.email.lower(), password_hash=hash_password(payload.password), full_name=payload.full_name,
                     role=payload.role, business_id=business.id)
        self.db.add(staff)
        self.db.flush()
        audit(self.db, actor.id, "STAFF_ADDED", "user", staff.id, role=payload.role)
        self.db.commit()
        return staff


def marketplace_status_out(db: Session, business: Business) -> dict:
    account = db.scalar(select(MarketplaceAccount).where(MarketplaceAccount.business_id == business.id))
    return {"business_name": business.name, "slug": business.slug, "status": account.status if account else "NOT_ENROLLED",
            "commission_rate": float(account.commission_rate) if account else None,
            "pickup_radius_km": float(account.pickup_radius_km) if account else None,
            "submitted_at": account.submitted_at if account else None, "approved_at": account.approved_at if account else None,
            "rejection_reason": account.rejection_reason if account else None,
            "checklist": BusinessProfileService(db).readiness(business)}
