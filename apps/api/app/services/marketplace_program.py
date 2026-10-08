"""Marketplace participation: enrolment, review, trials, activation, suspension and the lifecycle job.

Launder Business works without the Marketplace; joining is the laundry's choice. Four things are kept apart:

  review_status      Has Launder approved the laundry?   NOT_ENROLLED · INVITED · DRAFT · PENDING_REVIEW ·
                                                          CHANGES_REQUESTED · APPROVED · REJECTED
  commercial_status  On what terms?                      NONE · PENDING (trial waiting to start) · TRIAL · STANDARD ·
                                                          EXPIRED (trial over, standard terms not accepted)
  listing_status     May it appear?                      HIDDEN · LISTED · SUSPENDED (admin) · PAUSED_PLAN (plan)
  readiness          Is its setup complete?              computed, never stored

plus public ordering availability: the global `marketplace_mode` (OFF · PILOT · PUBLIC) and the launch cohort.
`MarketplaceAccount.status` is a summary of these for people and filters.

A laundry receives new Marketplace orders only when it is approved, has accepted the terms, is LISTED, is commercially
active (TRIAL running or STANDARD) and ordering is open for it. A trial's days are counted from that moment
(policy `WHEN_ORDERS_OPEN`), so nobody loses trial days while the Marketplace is closed.

Every value that shapes this (trial length and rate, approval, invitations, reminders, …) is a platform setting
administrators change in Admin → Monetization → Marketplace settings. Agreements snapshot the terms a laundry was
offered, so changing a setting never alters an agreement already made.
"""
import json
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from sqlalchemy import and_, false, func, select, true
from sqlalchemy.orm import Session

from ..core.errors import AppError, not_found
from ..domain import order_states as S
from ..domain.clock import as_utc, now_utc
from ..domain.money import percentage_of
from ..models import (
    Business,
    Commission,
    CommissionRule,
    MarketplaceAccount,
    MarketplaceAgreement,
    MarketplaceEvent,
    Order,
    Service,
    User,
)
from .audit import audit
from .billing import PLAN_PAUSE_REASON, notify_owner
from .commission import CommissionService, commission_terms
from .entitlements import require_feature, resolve
from .pricing import PricingAdmin, get_setting, pricing_audit, snapshot

DAY = timedelta(days=1)
MODES = ("OFF", "PILOT", "PUBLIC")
OPEN_AGREEMENT = ("OFFERED", "PENDING_START", "ACTIVE")
LIVE = ("TRIAL", "STANDARD")


def _bool(v) -> bool:
    return isinstance(v, bool)


def _int(lo: int, hi: int):
    return lambda v: isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi


def _rate(v) -> bool:
    try:
        d = Decimal(str(v))
    except (InvalidOperation, ValueError):
        return False
    return Decimal("0") <= d <= Decimal("50") and d == d.quantize(Decimal("0.01"))


# key: (validator, label, default). Defaults are used only when a row is missing; migration 0005 writes the rows.
MARKETPLACE_SETTINGS = {
    "marketplace_mode": (lambda v: v in MODES, "Public Marketplace: OFF, PILOT (launch cohort only) or PUBLIC", "PUBLIC"),
    "marketplace_self_enrollment": (_bool, "Laundries can apply by themselves", True),
    "marketplace_invitations": (_bool, "Admins can invite laundries", True),
    "marketplace_approval_required": (_bool, "Applications need admin approval", True),
    "marketplace_verification_required": (_bool, "Registration number or TIN required to join", False),
    "marketplace_auto_activate": (_bool, "List approved laundries automatically once ready", True),
    "marketplace_trial_enabled": (_bool, "Offer a Marketplace trial", True),
    "marketplace_trial_days": (_int(1, 365), "Trial length (days)", 30),
    "marketplace_trial_rate": (_rate, "Commission during the trial (%)", "0.00"),
    "marketplace_trial_start": (lambda v: v in ("WHEN_ORDERS_OPEN", "ON_APPROVAL"), "When the trial clock starts",
                                "WHEN_ORDERS_OPEN"),
    "marketplace_trial_one_per_business": (_bool, "One trial per laundry", True),
    "marketplace_trial_extension_allowed": (_bool, "Trials can be extended", True),
    "marketplace_trial_max_extensions": (_int(0, 12), "Maximum extensions per trial", 1),
    "marketplace_acceptance_required": (_bool, "After the trial, new orders pause until the laundry accepts the standard terms",
                                        True),
    "marketplace_reminder_days": (lambda v: isinstance(v, list) and len(v) <= 6 and all(_int(0, 60)(d) for d in v),
                                  "Trial reminders (days before the end)", [7, 2, 0]),
    "marketplace_suspension_pauses_trial": (_bool, "Suspended days are added back to a running trial", True),
}


def normalize_setting(key: str, value):
    if key == "marketplace_trial_rate" and _rate(value):
        return str(Decimal(str(value)).quantize(Decimal("0.01")))
    if key == "marketplace_reminder_days" and isinstance(value, list):
        return sorted(set(value), reverse=True)
    return value


def policy(db: Session) -> dict:
    out = {}
    for key, (_, _, default) in MARKETPLACE_SETTINGS.items():
        value = get_setting(db, key)
        out[key.removeprefix("marketplace_")] = default if value is None else value
    out["trial_rate"] = Decimal(str(out["trial_rate"]))
    return out


def summary_status(account: MarketplaceAccount) -> str:
    if account.review_status != "APPROVED":
        return account.review_status
    if account.listing_status in ("SUSPENDED", "PAUSED_PLAN"):
        return "SUSPENDED"
    if account.commercial_status == "EXPIRED":
        return "TRIAL_EXPIRED"
    if account.listing_status == "LISTED" and account.commercial_status == "TRIAL":
        return "TRIAL_ACTIVE"
    if account.listing_status == "LISTED" and account.commercial_status == "STANDARD":
        return "ACTIVE"
    return "APPROVED"  # approved, waiting for readiness, activation or the Marketplace to open


def visible_clause(mode: str):
    """SQL condition: the laundry may appear in discovery and receive new Marketplace orders."""
    if mode == "OFF":
        return false()
    return and_(MarketplaceAccount.review_status == "APPROVED", MarketplaceAccount.listing_status == "LISTED",
                MarketplaceAccount.commercial_status.in_(LIVE), Business.status == "ACTIVE",
                MarketplaceAccount.launch_cohort.is_(True) if mode == "PILOT" else true())


class MarketplaceProgram:
    def __init__(self, db: Session, actor: User | None = None):
        self.db, self.actor = db, actor
        self.policy = policy(db)

    # ---- reading ---------------------------------------------------------------------------------------------------
    def account(self, business_id: str, lock: bool = False) -> MarketplaceAccount:
        stmt = select(MarketplaceAccount).where(MarketplaceAccount.business_id == business_id)
        account = self.db.scalar(stmt.with_for_update() if lock else stmt)
        if account is None:
            account = MarketplaceAccount(business_id=business_id, status="NOT_ENROLLED", review_status="NOT_ENROLLED",
                                         commercial_status="NONE", listing_status="HIDDEN")
            self.db.add(account)
            self.db.flush()
        return account

    def open_agreement(self, business_id: str) -> MarketplaceAgreement | None:
        return self.db.scalar(select(MarketplaceAgreement).where(MarketplaceAgreement.business_id == business_id,
                                                                 MarketplaceAgreement.status.in_(OPEN_AGREEMENT)))

    def agreements(self, business_id: str) -> list[MarketplaceAgreement]:
        return list(self.db.scalars(select(MarketplaceAgreement).where(MarketplaceAgreement.business_id == business_id)
                                    .order_by(MarketplaceAgreement.version.desc())))

    def had_trial(self, business_id: str) -> bool:
        """A trial counts once it has started; one cancelled before it started does not."""
        return bool(self.db.scalar(select(MarketplaceAgreement.id).where(
            MarketplaceAgreement.business_id == business_id, MarketplaceAgreement.kind == "TRIAL",
            MarketplaceAgreement.starts_at.is_not(None))))

    def ordering_open(self, account: MarketplaceAccount) -> bool:
        mode = self.policy["mode"]
        return mode == "PUBLIC" or (mode == "PILOT" and account.launch_cohort)

    def accepting_orders(self, account: MarketplaceAccount, business: Business) -> bool:
        return (self.ordering_open(account) and account.review_status == "APPROVED" and account.listing_status == "LISTED"
                and account.commercial_status in LIVE and business.status == "ACTIVE")

    def standard_terms(self, business_id: str) -> dict:
        return commission_terms(CommissionService(self.db).rule_for(business_id, include_trials=False))

    def trial_offer(self, business_id: str) -> dict | None:
        """The trial this laundry would get if it joined now, or None. Never shows terms it is not eligible for."""
        p = self.policy
        if not p["trial_enabled"] or (p["trial_one_per_business"] and self.had_trial(business_id)):
            return None
        return {"days": p["trial_days"], "rate": float(p["trial_rate"]),
                "standard_rate": self.standard_terms(business_id)["rate"], "starts": p["trial_start"]}

    def readiness(self, business: Business, account: MarketplaceAccount | None = None) -> list[dict]:
        account = account or self.account(business.id)
        active, priced = self.db.execute(select(func.count(Service.id), func.count(Service.id).filter(Service.price > 0))
                                         .where(Service.business_id == business.id, Service.active.is_(True))).one()
        verification = self.policy["verification_required"]
        return [
            {"key": "profile", "done": bool(business.name and business.phone and business.description)},
            {"key": "location", "done": bool(business.area and business.address and business.latitude is not None)},
            {"key": "services", "done": active > 0},
            {"key": "prices", "done": active > 0 and priced == active},
            {"key": "hours", "done": any(not h.closed for h in business.hours)},
            {"key": "pickup", "done": not business.pickup_enabled or bool(account.pickup_radius_km and account.pickup_radius_km > 0),
             "applies": bool(business.pickup_enabled)},
            {"key": "verification", "done": not verification or bool(account.registration_number or account.tin),
             "applies": bool(verification)},
            {"key": "terms", "done": account.terms_accepted_at is not None},
        ]

    def missing(self, business: Business, account: MarketplaceAccount, ignore: tuple[str, ...] = ()) -> list[str]:
        return [c["key"] for c in self.readiness(business, account) if not c["done"] and c["key"] not in ignore]

    # ---- bookkeeping -----------------------------------------------------------------------------------------------
    def _event(self, account: MarketplaceAccount, action: str, before: str | None, reason: str = "", **data) -> None:
        account.status = summary_status(account)
        self.db.add(MarketplaceEvent(business_id=account.business_id, action=action, from_status=before,
                                     to_status=account.status, actor_id=self.actor.id if self.actor else None,
                                     reason=reason or "", data_json=json.dumps(data, default=str)))
        audit(self.db, self.actor.id if self.actor else None, f"MARKETPLACE_{action}", "marketplace_account",
              account.id or account.business_id, from_status=before, to_status=account.status, reason=reason or None)

    def _audit(self, action: str, agreement: MarketplaceAgreement, before: dict | None, reason: str) -> None:
        pricing_audit(self.db, self.actor, action, "marketplace_agreement", agreement.id, before,
                      snapshot(agreement, AGREEMENT_FIELDS), reason, agreement.business_id)

    def _new_agreement(self, business_id: str, kind: str, status: str, source: str, *, rate=None, days=None,
                       accepted_at=None, starts_at=None, terms: dict | None = None) -> MarketplaceAgreement:
        version = (self.db.scalar(select(func.max(MarketplaceAgreement.version))
                                  .where(MarketplaceAgreement.business_id == business_id)) or 0) + 1
        standard = Decimal(str(self.standard_terms(business_id)["rate"]))
        agreement = MarketplaceAgreement(
            business_id=business_id, version=version, kind=kind, status=status, source=source,
            rate=Decimal(rate).quantize(Decimal("0.01")) if rate is not None else None, standard_rate=standard,
            duration_days=days, accepted_at=accepted_at, accepted_by=None, starts_at=starts_at,
            terms_json=json.dumps(terms or {}), created_by=self.actor.id if self.actor else None)
        self.db.add(agreement)
        self.db.flush()
        return agreement

    def _trial_terms(self, business_id: str, days: int | None, rate) -> tuple[int, Decimal, str]:
        p = self.policy
        custom = days is not None or rate is not None
        days = p["trial_days"] if days is None else days
        rate = p["trial_rate"] if rate is None else Decimal(str(rate))
        if not (1 <= days <= 365):
            raise AppError(422, "INVALID_TRIAL", "A trial lasts between 1 and 365 days")
        if not _rate(rate):
            raise AppError(422, "INVALID_RATE", "Trial commission must be between 0 % and 50 %")
        return days, Decimal(rate), "CUSTOM" if custom else "DEFAULT_POLICY"

    def _offer_trial(self, account: MarketplaceAccount, status: str, source_hint: str, days=None, rate=None,
                     reason: str = "") -> MarketplaceAgreement | None:
        """Create the trial agreement (or None when trials are off / already used and no custom terms were given)."""
        p = self.policy
        custom = days is not None or rate is not None
        if not custom and not p["trial_enabled"]:
            return None
        if p["trial_one_per_business"] and self.had_trial(account.business_id):
            if custom:
                raise AppError(409, "TRIAL_ALREADY_USED", "This laundry has already had a Marketplace trial")
            return None
        days, rate, source = self._trial_terms(account.business_id, days, rate)
        standard = self.standard_terms(account.business_id)
        source = "INVITATION" if source_hint == "INVITATION" else source
        agreement = self._new_agreement(account.business_id, "TRIAL", status, source, rate=rate, days=days,
                                        terms={"trial_days": days, "trial_rate": str(rate), "standard": standard,
                                               "starts": p["trial_start"], "acceptance_required": p["acceptance_required"]})
        self._audit("MARKETPLACE_TRIAL_OFFERED", agreement, None, reason or source)
        return agreement

    def _standard(self, account: MarketplaceAccount, accepted_at: datetime, at: datetime, reason: str) -> MarketplaceAgreement:
        agreement = self._new_agreement(account.business_id, "STANDARD", "ACTIVE", "DEFAULT_POLICY", accepted_at=accepted_at,
                                        starts_at=at, terms={"standard": self.standard_terms(account.business_id)})
        agreement.accepted_by = self.actor.id if self.actor else None
        account.commercial_status = "STANDARD"
        self._audit("MARKETPLACE_STANDARD_TERMS", agreement, None, reason)
        return agreement

    def _rule_window_clash(self, business_id: str, start: datetime, end: datetime, ignore: str | None = None) -> bool:
        stmt = select(CommissionRule.id).where(CommissionRule.scope == "PROMOTION", CommissionRule.business_id == business_id,
                                               CommissionRule.effective_from < end,
                                               (CommissionRule.effective_to.is_(None)) | (CommissionRule.effective_to > start))
        if ignore:
            stmt = stmt.where(CommissionRule.id != ignore)
        return bool(self.db.scalar(stmt))

    def _start_trial(self, account: MarketplaceAccount, agreement: MarketplaceAgreement, at: datetime) -> None:
        end = at + timedelta(days=agreement.duration_days)
        if self._rule_window_clash(account.business_id, at, end):
            raise AppError(409, "OVERLAPPING_RULE", "This laundry has a commission promotion during the trial dates; "
                           "end it first so the promised trial applies")
        rule = PricingAdmin(self.db, self.actor).create_rule(
            "PROMOTION", account.business_id, agreement.rate, 0, False, True, at, end,
            f"Marketplace trial v{agreement.version}", commit=False, agreement_id=agreement.id, allow_past=True)
        before = snapshot(agreement, AGREEMENT_FIELDS)
        agreement.status, agreement.starts_at, agreement.ends_at, agreement.commission_rule_id = "ACTIVE", at, end, rule.id
        account.commercial_status = "TRIAL"
        self._audit("MARKETPLACE_TRIAL_STARTED", agreement, before, "Trial started")
        business = self.db.get(Business, account.business_id)
        notify_owner(self.db, business, "MARKETPLACE_TRIAL_STARTED", agreement.id, ends_at=end.isoformat(),
                     rate=str(agreement.rate), days=agreement.duration_days)

    def _close_trial(self, account: MarketplaceAccount, agreement: MarketplaceAgreement, at: datetime, why: str,
                     reason: str) -> None:
        """End a running trial at `at` and move to standard terms if accepted, otherwise pause new orders."""
        before = snapshot(agreement, AGREEMENT_FIELDS)
        rule = self.db.get(CommissionRule, agreement.commission_rule_id) if agreement.commission_rule_id else None
        if rule and (rule.effective_to is None or as_utc(rule.effective_to) > at):
            rule.effective_to = at
        agreement.status, agreement.end_reason, agreement.ends_at = "ENDED", why, at
        self._audit("MARKETPLACE_TRIAL_ENDED", agreement, before, reason)
        business = self.db.get(Business, account.business_id)
        accepted = account.post_trial_accepted_at or (None if self.policy["acceptance_required"] else account.terms_accepted_at)
        if accepted:
            self._standard(account, accepted, at, "Trial ended; standard terms accepted")
            notify_owner(self.db, business, "MARKETPLACE_TRIAL_CONVERTED", agreement.id)
        else:
            account.commercial_status = "EXPIRED"
            notify_owner(self.db, business, "MARKETPLACE_TRIAL_EXPIRED", agreement.id)

    def _try_activate(self, account: MarketplaceAccount, at: datetime, manual: bool = False) -> bool:
        """List an approved laundry and start a waiting trial when everything allows it. Returns True if anything changed."""
        if account.review_status != "APPROVED" or account.listing_status in ("SUSPENDED", "PAUSED_PLAN"):
            return False
        changed = False
        business = self.db.get(Business, account.business_id)
        if account.listing_status == "HIDDEN":
            if not (manual or self.policy["auto_activate"]) or self.missing(business, account):
                return False
            account.listing_status = "LISTED"
            account.first_listed_at = account.first_listed_at or at
            changed = True
        agreement = self.open_agreement(account.business_id)
        if (account.commercial_status == "PENDING" and agreement and agreement.status == "PENDING_START"
                and (self.ordering_open(account) or self.policy["trial_start"] == "ON_APPROVAL")):
            self._start_trial(account, agreement, at)
            changed = True
        return changed

    # ---- provider --------------------------------------------------------------------------------------------------
    def _application_fields(self, account: MarketplaceAccount, data: dict) -> None:
        for key in ("contact_name", "registration_number", "tin"):
            if key in data:
                setattr(account, key, (data[key] or "").strip() or None)
        if data.get("pickup_radius_km") is not None:
            account.pickup_radius_km = Decimal(str(data["pickup_radius_km"]))

    def save_draft(self, business: Business, data: dict) -> MarketplaceAccount:
        account = self.account(business.id, lock=True)
        if account.review_status not in ("NOT_ENROLLED", "DRAFT", "CHANGES_REQUESTED", "REJECTED", "INVITED"):
            raise AppError(409, "APPLICATION_LOCKED", "This application can no longer be edited")
        if account.review_status != "INVITED" and not self.policy["self_enrollment"]:
            raise AppError(403, "ENROLLMENT_CLOSED", "Marketplace applications are by invitation at the moment")
        before = account.status
        self._application_fields(account, data)
        if account.review_status in ("NOT_ENROLLED", "REJECTED"):
            account.review_status = "DRAFT"
        self._event(account, "DRAFT_SAVED", before)
        self.db.commit()
        return account

    def submit(self, business: Business, data: dict) -> MarketplaceAccount:
        account = self.account(business.id, lock=True)
        invited = account.review_status == "INVITED"
        if account.review_status not in ("NOT_ENROLLED", "DRAFT", "CHANGES_REQUESTED", "REJECTED", "INVITED"):
            raise AppError(409, "APPLICATION_EXISTS", f"Marketplace application is already {account.status}")
        if not invited and not self.policy["self_enrollment"]:
            raise AppError(403, "ENROLLMENT_CLOSED", "Marketplace applications are by invitation at the moment")
        if not data.get("accept_terms"):
            raise AppError(422, "TERMS_REQUIRED", "Accept the Marketplace terms to continue")
        require_feature(self.db, business.id, "marketplace_eligible")
        self._application_fields(account, data)
        missing = self.missing(business, account, ignore=("terms",))
        if missing:
            raise AppError(409, "NOT_READY", "Complete your business setup before applying", {"missing": missing})
        now = now_utc()
        before = account.status
        account.terms_accepted_at, account.submitted_at, account.rejection_reason = now, now, None
        if data.get("accept_post_trial"):
            account.post_trial_accepted_at = now
        if invited or not self.policy["approval_required"]:
            account.review_status, account.approved_at = "APPROVED", now
            business.verification_status = "VERIFIED"
            if business.status == "ONBOARDING":
                business.status = "ACTIVE"
            self._commercial_after_approval(account, now, offered=self.open_agreement(business.id))
            self._event(account, "INVITATION_ACCEPTED" if invited else "AUTO_APPROVED", before)
            self._try_activate(account, now)
            account.status = summary_status(account)
        else:
            account.review_status = "PENDING_REVIEW"
            self._event(account, "SUBMITTED", before)
        self.db.commit()
        return account

    def _commercial_after_approval(self, account: MarketplaceAccount, at: datetime, offered: MarketplaceAgreement | None,
                                   days=None, rate=None, skip_trial: bool = False, reason: str = "") -> None:
        if offered and offered.status == "OFFERED":
            if skip_trial:
                offered.status, offered.end_reason = "CANCELLED", "CANCELLED"
            else:
                offered.status, offered.accepted_at = "PENDING_START", account.terms_accepted_at or at
                account.commercial_status = "PENDING"
                return
        trial = None if skip_trial else self._offer_trial(account, "PENDING_START", "DEFAULT_POLICY", days, rate, reason)
        if trial:
            trial.accepted_at = account.terms_accepted_at or at
            account.commercial_status = "PENDING"
        else:
            self._standard(account, account.terms_accepted_at or at, at, "Approved on standard terms")

    def accept_standard_terms(self, business: Business) -> MarketplaceAccount:
        account = self.account(business.id, lock=True)
        if account.review_status != "APPROVED":
            raise AppError(409, "NOT_APPROVED", "Your Marketplace application has not been approved yet")
        now = now_utc()
        before = account.status
        if account.commercial_status in ("TRIAL", "PENDING"):
            if account.post_trial_accepted_at:
                raise AppError(409, "ALREADY_ACCEPTED", "You have already accepted the terms after your trial")
            account.post_trial_accepted_at = now
            self._event(account, "POST_TRIAL_TERMS_ACCEPTED", before)
        elif account.commercial_status in ("EXPIRED", "NONE"):
            require_feature(self.db, business.id, "marketplace_eligible")
            account.post_trial_accepted_at = now
            self._standard(account, now, now, "Accepted by the laundry")
            self._try_activate(account, now)
            self._event(account, "STANDARD_TERMS_ACCEPTED", before)
        else:
            raise AppError(409, "ALREADY_ACCEPTED", "You are already on the standard Marketplace terms")
        self.db.commit()
        return account

    # ---- admin: review ---------------------------------------------------------------------------------------------
    def invite(self, business: Business, note: str, trial_days: int | None = None, trial_rate=None,
               launch_cohort: bool | None = None) -> MarketplaceAccount:
        if not self.policy["invitations"]:
            raise AppError(403, "INVITATIONS_DISABLED", "Invitations are switched off in Marketplace settings")
        account = self.account(business.id, lock=True)
        if account.review_status not in ("NOT_ENROLLED", "DRAFT", "REJECTED", "CHANGES_REQUESTED"):
            raise AppError(409, "INVALID_TRANSITION", f"Cannot invite a laundry that is {account.status}")
        require_feature(self.db, business.id, "marketplace_eligible")
        before = account.status
        account.review_status, account.invited_at, account.invited_by = "INVITED", now_utc(), self.actor.id
        account.invitation_note, account.rejection_reason = note or None, None
        if launch_cohort is not None:
            account.launch_cohort = launch_cohort
        existing = self.open_agreement(business.id)
        if existing and existing.status == "OFFERED":
            existing.status, existing.end_reason = "CANCELLED", "SUPERSEDED"
            self.db.flush()
        self._offer_trial(account, "OFFERED", "INVITATION", trial_days, trial_rate, note)
        self._event(account, "INVITED", before, note, trial_days=trial_days, trial_rate=trial_rate)
        notify_owner(self.db, business, "MARKETPLACE_INVITED", f"{account.id}:{account.invited_at.isoformat()}")
        self.db.commit()
        return account

    def approve(self, account: MarketplaceAccount, reason: str = "", trial_days: int | None = None, trial_rate=None,
                skip_trial: bool = False) -> MarketplaceAccount:
        if account.review_status != "PENDING_REVIEW":
            raise AppError(409, "INVALID_TRANSITION", f"Cannot approve an application that is {account.status}")
        require_feature(self.db, account.business_id, "marketplace_eligible")  # before anything changes
        now = now_utc()
        before = account.status
        business = self.db.get(Business, account.business_id)
        account.review_status, account.approved_at = "APPROVED", now
        account.reviewed_at, account.reviewed_by = now, self.actor.id
        business.verification_status = "VERIFIED"
        if business.status == "ONBOARDING":
            business.status = "ACTIVE"
        self._commercial_after_approval(account, now, self.open_agreement(account.business_id), trial_days, trial_rate,
                                        skip_trial, reason)
        self._try_activate(account, now)
        self._event(account, "APPROVED", before, reason, trial_days=trial_days, trial_rate=trial_rate, skip_trial=skip_trial)
        notify_owner(self.db, business, "MARKETPLACE_APPROVED", account.id)
        self.db.commit()
        return account

    def request_changes(self, account: MarketplaceAccount, reason: str) -> MarketplaceAccount:
        return self._review_decision(account, "CHANGES_REQUESTED", reason, "MARKETPLACE_CHANGES_REQUESTED")

    def reject(self, account: MarketplaceAccount, reason: str) -> MarketplaceAccount:
        return self._review_decision(account, "REJECTED", reason, "MARKETPLACE_REJECTED")

    def _review_decision(self, account: MarketplaceAccount, target: str, reason: str, notice: str) -> MarketplaceAccount:
        if not (reason and reason.strip()):
            raise AppError(422, "REASON_REQUIRED", "A reason is required for this decision")
        allowed = {"CHANGES_REQUESTED": ("PENDING_REVIEW",), "REJECTED": ("PENDING_REVIEW", "CHANGES_REQUESTED", "INVITED")}
        if account.review_status not in allowed[target]:
            raise AppError(409, "INVALID_TRANSITION", f"Cannot do this to an application that is {account.status}")
        before = account.status
        account.review_status, account.rejection_reason = target, reason.strip()
        account.reviewed_at, account.reviewed_by = now_utc(), self.actor.id
        offered = self.open_agreement(account.business_id)
        if target == "REJECTED" and offered and offered.status == "OFFERED":
            offered.status, offered.end_reason = "CANCELLED", "CANCELLED"
        self._event(account, target, before, reason)
        notify_owner(self.db, self.db.get(Business, account.business_id), notice, f"{account.id}:{account.reviewed_at.isoformat()}",
                     reason=reason)
        self.db.commit()
        return account

    # ---- admin: listing --------------------------------------------------------------------------------------------
    def activate(self, account: MarketplaceAccount, reason: str = "") -> MarketplaceAccount:
        if account.review_status != "APPROVED" or account.listing_status != "HIDDEN":
            raise AppError(409, "INVALID_TRANSITION", f"Cannot activate a laundry that is {account.status}")
        if account.commercial_status in ("NONE", "EXPIRED"):
            raise AppError(409, "TERMS_NOT_ACCEPTED", "The laundry has not accepted Marketplace terms yet")
        business = self.db.get(Business, account.business_id)
        missing = self.missing(business, account)
        if missing:
            raise AppError(409, "NOT_READY", "The laundry's setup is not complete", {"missing": missing})
        before = account.status
        self._try_activate(account, now_utc(), manual=True)
        self._event(account, "ACTIVATED", before, reason)
        self.db.commit()
        return account

    def suspend(self, account: MarketplaceAccount, reason: str) -> MarketplaceAccount:
        if not (reason and reason.strip()):
            raise AppError(422, "REASON_REQUIRED", "A reason is required for this decision")
        if account.review_status != "APPROVED" or account.listing_status == "SUSPENDED":
            raise AppError(409, "INVALID_TRANSITION", f"Cannot suspend a laundry that is {account.status}")
        before = account.status
        account.listing_status, account.status_reason, account.suspended_at = "SUSPENDED", reason.strip(), now_utc()
        account.reviewed_at, account.reviewed_by = account.suspended_at, self.actor.id
        self._event(account, "SUSPENDED", before, reason)
        notify_owner(self.db, self.db.get(Business, account.business_id), "MARKETPLACE_SUSPENDED",
                     f"{account.id}:{account.suspended_at.isoformat()}", reason=reason)
        self.db.commit()
        return account

    def reactivate(self, account: MarketplaceAccount, reason: str = "") -> MarketplaceAccount:
        if account.listing_status != "SUSPENDED":
            raise AppError(409, "INVALID_TRANSITION", f"Cannot reactivate a laundry that is {account.status}")
        require_feature(self.db, account.business_id, "marketplace_eligible")
        now = now_utc()
        before = account.status
        trial = self.open_agreement(account.business_id)
        added = None
        if (trial and trial.kind == "TRIAL" and trial.status == "ACTIVE" and account.suspended_at
                and self.policy["suspension_pauses_trial"]):
            paused = now - max(as_utc(account.suspended_at), as_utc(trial.starts_at))
            if paused > timedelta(0):
                added = self._move_trial_end(trial, as_utc(trial.ends_at) + paused, "Suspended days added back")
        account.listing_status, account.status_reason, account.suspended_at = "LISTED", None, None
        account.reviewed_at, account.reviewed_by = now, self.actor.id
        self._event(account, "REACTIVATED", before, reason, trial_days_added=added)
        notify_owner(self.db, self.db.get(Business, account.business_id), "MARKETPLACE_REACTIVATED", f"{account.id}:{now.isoformat()}")
        self.db.commit()
        return account

    def set_launch_cohort(self, account: MarketplaceAccount, included: bool, reason: str = "") -> MarketplaceAccount:
        before = account.status
        account.launch_cohort = included
        self._event(account, "COHORT_ADDED" if included else "COHORT_REMOVED", before, reason)
        self._try_activate(account, now_utc())
        account.status = summary_status(account)
        self.db.commit()
        return account

    # ---- admin: trials ---------------------------------------------------------------------------------------------
    def _move_trial_end(self, trial: MarketplaceAgreement, new_end: datetime, reason: str) -> float:
        """The only change a running trial allows: its end moves later. Its rate never changes."""
        rule = self.db.get(CommissionRule, trial.commission_rule_id)
        if self._rule_window_clash(trial.business_id, as_utc(trial.ends_at), new_end, ignore=rule.id if rule else None):
            raise AppError(409, "OVERLAPPING_RULE", "Another commission promotion starts during the extension")
        before = snapshot(trial, AGREEMENT_FIELDS)
        added = (new_end - as_utc(trial.ends_at)).total_seconds() / 86400
        trial.ends_at = new_end
        if rule:
            rule_before = snapshot(rule, RULE_FIELDS)
            rule.effective_to = new_end
            pricing_audit(self.db, self.actor, "COMMISSION_RULE_EXTENDED", "commission_rule", rule.id, rule_before,
                          snapshot(rule, RULE_FIELDS), reason, rule.business_id)
        self._audit("MARKETPLACE_TRIAL_EXTENDED", trial, before, reason)
        return round(added, 2)

    def grant_trial(self, account: MarketplaceAccount, reason: str, days: int | None = None, rate=None) -> MarketplaceAccount:
        if account.review_status != "APPROVED":
            raise AppError(409, "NOT_APPROVED", "Approve the laundry before granting a trial")
        if account.commercial_status in ("PENDING", "TRIAL"):
            raise AppError(409, "TRIAL_EXISTS", "This laundry already has a trial; extend it instead")
        if not (reason and reason.strip()):
            raise AppError(422, "REASON_REQUIRED", "A reason is required")
        if self.policy["trial_one_per_business"] and self.had_trial(account.business_id):
            raise AppError(409, "TRIAL_ALREADY_USED", "This laundry has already had a Marketplace trial")
        now = now_utc()
        before = account.status
        current = self.open_agreement(account.business_id)
        if current and current.kind == "STANDARD":
            # Already on standard terms: they continue after the trial, which only lowers commission meanwhile.
            current.status, current.end_reason, current.ends_at = "ENDED", "SUPERSEDED", now
            account.post_trial_accepted_at = account.post_trial_accepted_at or current.accepted_at or now
            self.db.flush()
        days, rate, _ = self._trial_terms(account.business_id, days, rate)
        trial = self._offer_trial(account, "PENDING_START", "CUSTOM", days, rate, reason)
        trial.accepted_at = account.terms_accepted_at or now
        account.commercial_status = "PENDING"
        self._try_activate(account, now)
        self._event(account, "TRIAL_GRANTED", before, reason, days=days, rate=str(rate))
        self.db.commit()
        return account

    def extend_trial(self, account: MarketplaceAccount, days: int, reason: str) -> MarketplaceAccount:
        if not (reason and reason.strip()):
            raise AppError(422, "REASON_REQUIRED", "A reason is required")
        if not (1 <= days <= 365):
            raise AppError(422, "INVALID_TRIAL", "Extend by 1 to 365 days")
        trial = self.open_agreement(account.business_id)
        if not trial or trial.kind != "TRIAL":
            raise AppError(409, "NO_TRIAL", "This laundry has no trial to extend")
        p = self.policy
        if not p["trial_extension_allowed"]:
            raise AppError(409, "EXTENSIONS_DISABLED", "Trial extensions are switched off in Marketplace settings")
        if trial.extensions >= p["trial_max_extensions"]:
            raise AppError(409, "EXTENSION_LIMIT", f"This trial has already been extended {trial.extensions} time(s)")
        before = account.status
        if trial.status == "ACTIVE":
            self._move_trial_end(trial, as_utc(trial.ends_at) + timedelta(days=days), reason)
        else:
            snap = snapshot(trial, AGREEMENT_FIELDS)
            trial.duration_days += days
            self._audit("MARKETPLACE_TRIAL_EXTENDED", trial, snap, reason)
        trial.extensions += 1
        self._event(account, "TRIAL_EXTENDED", before, reason, days=days)
        notify_owner(self.db, self.db.get(Business, account.business_id), "MARKETPLACE_TRIAL_EXTENDED",
                     f"{trial.id}:{trial.extensions}", days=days)
        self.db.commit()
        return account

    def end_trial(self, account: MarketplaceAccount, reason: str) -> MarketplaceAccount:
        """Safeguards: a reason is required, the laundry is told, orders already placed keep their trial rate, and
        the laundry is moved to standard terms only if it accepted them; otherwise new orders pause."""
        if not (reason and reason.strip()):
            raise AppError(422, "REASON_REQUIRED", "A reason is required")
        trial = self.open_agreement(account.business_id)
        if not trial or trial.kind != "TRIAL":
            raise AppError(409, "NO_TRIAL", "This laundry has no trial to end")
        before = account.status
        if trial.status == "ACTIVE":
            self._close_trial(account, trial, now_utc(), "ENDED_EARLY", reason)
        else:
            snap = snapshot(trial, AGREEMENT_FIELDS)
            trial.status, trial.end_reason = "CANCELLED", "CANCELLED"
            self._audit("MARKETPLACE_TRIAL_CANCELLED", trial, snap, reason)
            if account.review_status == "APPROVED":
                accepted = account.post_trial_accepted_at or (None if self.policy["acceptance_required"]
                                                              else account.terms_accepted_at)
                if accepted:
                    self._standard(account, accepted, now_utc(), "Trial cancelled; standard terms accepted")
                else:
                    account.commercial_status = "EXPIRED"
        self._event(account, "TRIAL_ENDED_EARLY", before, reason)
        self.db.commit()
        return account

    # ---- lifecycle -------------------------------------------------------------------------------------------------
    def run(self, at: datetime | None = None, commit: bool = True) -> dict:
        """Idempotent; safe to repeat or run late. Starts waiting trials when ordering opens, sends reminders,
        ends trials, and follows plan eligibility."""
        at = at or now_utc()
        stats = {"trials_started": 0, "trial_reminders": 0, "trials_ended": 0, "trials_converted": 0,
                 "marketplace_paused": 0, "marketplace_restored": 0, "start_blocked": 0}
        days = sorted(self.policy["reminder_days"])
        for account in list(self.db.scalars(select(MarketplaceAccount).where(
                MarketplaceAccount.review_status == "APPROVED",
                MarketplaceAccount.commercial_status.in_(("PENDING", "TRIAL"))).with_for_update(skip_locked=True))):
            trial = self.open_agreement(account.business_id)
            business = self.db.get(Business, account.business_id)
            if account.commercial_status == "PENDING":
                before = account.status
                try:
                    with self.db.begin_nested():
                        if self._try_activate(account, at):
                            if account.commercial_status == "TRIAL":
                                stats["trials_started"] += 1
                            self._event(account, "TRIAL_STARTED" if account.commercial_status == "TRIAL" else "ACTIVATED",
                                        before)
                except AppError as exc:
                    stats["start_blocked"] += 1
                    notify_owner(self.db, business, "MARKETPLACE_TRIAL_BLOCKED", trial.id if trial else account.id,
                                 code=exc.code)
                continue
            if not trial or trial.kind != "TRIAL" or trial.status != "ACTIVE":
                continue
            if account.listing_status == "SUSPENDED" and self.policy["suspension_pauses_trial"]:
                continue  # the clock is paused; reactivation adds the suspended days back
            ends = as_utc(trial.ends_at)
            if ends <= at:
                before = account.status
                self._close_trial(account, trial, ends, "EXPIRED", "Trial period over")
                stats["trials_ended"] += 1
                stats["trials_converted"] += account.commercial_status == "STANDARD"
                self._event(account, "TRIAL_EXPIRED" if account.commercial_status == "EXPIRED" else "TRIAL_CONVERTED", before)
                continue
            due = [d for d in days if d > 0 and ends - timedelta(days=d) <= at]
            if due:  # only the most urgent reminder, even if the job ran late and several are due
                before_count = self._notice_count(business)
                notify_owner(self.db, business, "MARKETPLACE_TRIAL_ENDING", f"{trial.id}:{due[0]}:{trial.extensions}",
                             days=due[0], ends_at=ends.isoformat(), standard_rate=str(trial.standard_rate))
                stats["trial_reminders"] += self._notice_count(business) - before_count
        stats["marketplace_paused"], stats["marketplace_restored"] = self._plan_eligibility(at)
        if commit:
            self.db.commit()
        else:
            self.db.flush()
        return stats

    def _notice_count(self, business: Business) -> int:
        from ..models import Notification

        self.db.flush()
        return self.db.scalar(select(func.count(Notification.id)).where(Notification.user_id == business.owner_id)) or 0

    def _plan_eligibility(self, at: datetime) -> tuple[int, int]:
        """Listings follow plan eligibility automatically. Only pauses made by this rule are undone by it;
        suspensions decided by an administrator are never lifted here."""
        paused = restored = 0
        for account in list(self.db.scalars(select(MarketplaceAccount).where(
                MarketplaceAccount.listing_status.in_(("LISTED", "PAUSED_PLAN"))))):
            eligible = "marketplace_eligible" in resolve(self.db, account.business_id, at).features
            business = self.db.get(Business, account.business_id)
            before = account.status
            if account.listing_status == "LISTED" and not eligible:
                account.listing_status, account.status_reason = "PAUSED_PLAN", PLAN_PAUSE_REASON
                self._event(account, "PAUSED_BY_PLAN", before, PLAN_PAUSE_REASON)
                notify_owner(self.db, business, "MARKETPLACE_PAUSED", f"{account.id}:{at.date()}")
                paused += 1
            elif account.listing_status == "PAUSED_PLAN" and eligible:
                account.listing_status, account.status_reason = "LISTED", None
                self._event(account, "RESTORED_BY_PLAN", before)
                notify_owner(self.db, business, "MARKETPLACE_RESTORED", f"{account.id}:{at.date()}")
                restored += 1
        return paused, restored

    # ---- views -----------------------------------------------------------------------------------------------------
    def agreement_out(self, a: MarketplaceAgreement | None, at: datetime | None = None) -> dict | None:
        if a is None:
            return None
        at = at or now_utc()
        days_left = None
        if a.status == "ACTIVE" and a.ends_at:
            import math

            days_left = max(0, math.ceil((as_utc(a.ends_at) - at).total_seconds() / 86400))
        return {"id": a.id, "version": a.version, "kind": a.kind, "status": a.status, "source": a.source,
                "rate": float(a.rate) if a.rate is not None else None,
                "standard_rate": float(a.standard_rate) if a.standard_rate is not None else None,
                "duration_days": a.duration_days, "starts_at": a.starts_at, "ends_at": a.ends_at, "days_left": days_left,
                "extensions": a.extensions, "accepted_at": a.accepted_at, "end_reason": a.end_reason,
                "terms": json.loads(a.terms_json or "{}"), "created_at": a.created_at}

    def trial_stats(self, business_id: str, agreement: MarketplaceAgreement | None) -> dict | None:
        """What the laundry got from its trial: orders, sales, commission charged and saved, new customers."""
        if not agreement or agreement.kind != "TRIAL" or not agreement.starts_at:
            return None
        live = Order.status.notin_([S.CANCELLED, S.REJECTED])
        orders = list(self.db.scalars(select(Order).where(Order.business_id == business_id, Order.source == "MARKETPLACE",
                                                          Order.marketplace_agreement_id == agreement.id, live)))
        ids = [o.id for o in orders]
        charged, waived = (0, 0)
        settled: set[str] = set()
        if ids:
            charged, waived = self.db.execute(select(func.coalesce(func.sum(Commission.amount), 0),
                                                     func.coalesce(func.sum(Commission.waived_amount), 0))
                                              .where(Commission.order_id.in_(ids))).one()
            settled = set(self.db.scalars(select(Commission.order_id).where(Commission.order_id.in_(ids),
                                                                           Commission.entry_type == "EARNED")))
        pending_saving = 0
        for o in orders:
            if o.id not in settled and o.commission_standard_rate is not None and o.commission_rate is not None:
                basis = max(o.subtotal - o.discount, 0)
                pending_saving += max(percentage_of(basis, o.commission_standard_rate) - percentage_of(basis, o.commission_rate), 0)
        first = (select(Order.customer_id, func.min(Order.created_at).label("first_at"))
                 .where(Order.business_id == business_id, live).group_by(Order.customer_id).subquery())
        new_customers = self.db.scalar(select(func.count()).select_from(Order).join(
            first, and_(first.c.customer_id == Order.customer_id, first.c.first_at == Order.created_at)).where(
            Order.business_id == business_id, Order.marketplace_agreement_id == agreement.id, live)) or 0
        return {"orders": len(orders), "sales": sum(o.total for o in orders), "commission_charged": int(charged),
                "commission_saved": int(waived) + pending_saving, "commission_saved_settled": int(waived),
                "new_customers": new_customers}

    def provider_view(self, business: Business) -> dict:
        account = self.account(business.id)
        agreement = self.open_agreement(business.id)
        last_trial = agreement if agreement and agreement.kind == "TRIAL" else self.db.scalar(
            select(MarketplaceAgreement).where(MarketplaceAgreement.business_id == business.id,
                                               MarketplaceAgreement.kind == "TRIAL",
                                               MarketplaceAgreement.starts_at.is_not(None))
            .order_by(MarketplaceAgreement.version.desc()))
        now = now_utc()
        rule = CommissionService(self.db).rule_for(business.id)
        can_apply = account.review_status == "INVITED" or (
            self.policy["self_enrollment"] and account.review_status in ("NOT_ENROLLED", "DRAFT", "CHANGES_REQUESTED", "REJECTED"))
        offer = None
        if account.review_status in ("NOT_ENROLLED", "DRAFT", "CHANGES_REQUESTED", "REJECTED", "PENDING_REVIEW"):
            offer = self.trial_offer(business.id)
        if agreement and agreement.status == "OFFERED":
            offer = {"days": agreement.duration_days, "rate": float(agreement.rate),
                     "standard_rate": float(agreement.standard_rate), "starts": self.policy["trial_start"]}
        return {
            "business_name": business.name, "slug": business.slug, "status": account.status,
            "review_status": account.review_status, "commercial_status": account.commercial_status,
            "listing_status": account.listing_status, "ordering_open": self.ordering_open(account),
            "accepting_orders": self.accepting_orders(account, business), "can_apply": can_apply,
            "self_enrollment": self.policy["self_enrollment"],
            "application": {"contact_name": account.contact_name, "registration_number": account.registration_number,
                            "tin": account.tin, "pickup_radius_km": float(account.pickup_radius_km or 0) or None},
            "submitted_at": account.submitted_at, "approved_at": account.approved_at,
            "terms_accepted_at": account.terms_accepted_at, "post_trial_accepted_at": account.post_trial_accepted_at,
            "acceptance_required": self.policy["acceptance_required"],
            "rejection_reason": account.rejection_reason, "status_reason": account.status_reason,
            "invitation": {"invited_at": account.invited_at, "note": account.invitation_note}
            if account.review_status == "INVITED" else None,
            "offer": offer, "standard_terms": self.standard_terms(business.id),
            "agreement": self.agreement_out(agreement, now), "last_trial": self.agreement_out(last_trial, now),
            "trial_stats": self.trial_stats(business.id, last_trial),
            "commission_rate": float(rule.rate), "commission_terms": commission_terms(rule),
            "pickup_radius_km": float(account.pickup_radius_km) if account.pickup_radius_km else None,
            "listing_fee": get_setting(self.db, "marketplace_listing_fee") or 0,
            "checklist": self.readiness(business, account),
        }

    def history(self, business_id: str, limit: int = 50) -> list[dict]:
        rows = list(self.db.scalars(select(MarketplaceEvent).where(MarketplaceEvent.business_id == business_id)
                                    .order_by(MarketplaceEvent.created_at.desc()).limit(limit)))
        actors = {r.actor_id for r in rows if r.actor_id}
        emails = dict(self.db.execute(select(User.id, User.email).where(User.id.in_(actors))).all()) if actors else {}
        return [{"action": r.action, "from_status": r.from_status, "to_status": r.to_status, "reason": r.reason,
                 "actor": emails.get(r.actor_id, "system") if r.actor_id else "system",
                 "data": json.loads(r.data_json or "{}"), "created_at": r.created_at} for r in rows]


def account_or_404(db: Session, business_id: str) -> MarketplaceAccount:
    if not db.get(Business, business_id):
        raise not_found("Business")
    return MarketplaceProgram(db).account(business_id, lock=True)


AGREEMENT_FIELDS = ("business_id", "version", "kind", "status", "rate", "standard_rate", "duration_days", "starts_at",
                    "ends_at", "extensions", "source", "accepted_at", "end_reason")
RULE_FIELDS = ("scope", "business_id", "rate", "effective_from", "effective_to", "reason")
