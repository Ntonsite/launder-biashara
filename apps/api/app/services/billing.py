"""Subscriptions, invoices, payments and the billing cycle.

Nothing is ever charged automatically: an invoice is a request to pay, and a payment exists only when Launder finance
records money actually received (cash, bank transfer, or mobile money to Launder's account). Live mobile-money
collection for subscriptions needs a payment gateway and is not connected yet.

Lifecycle
  subscribe free plan        → ACTIVE, no invoices
  subscribe paid plan        → TRIALING for the plan's trial days (first time only), else ACTIVE with an OPEN invoice
  trial ends                 → ACTIVE, invoice for the first period
  period ends                → next period and its invoice (one per period, enforced by a unique key)
  invoice unpaid after due   → PAST_DUE; after the plan's grace days → EXPIRED, invoice voided, default plan applies
  upgrade                    → immediate; unused paid time on the old plan is credited on the new invoice
  downgrade / cancel         → at the end of the paid period
Business terms (complimentary, fixed price, percentage) are applied when each invoice is issued and shown as lines.
"""
import json
from calendar import monthrange
from datetime import datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.errors import AppError, not_found
from ..domain import order_states as S
from ..domain.clock import as_utc, now_utc
from ..domain.money import percentage_of
from ..models import (
    Business,
    BusinessSubscription,
    CommercialOverride,
    Commission,
    InvoiceLine,
    MarketplaceAccount,
    Notification,
    Order,
    PilotEnrollment,
    PilotProgram,
    SubscriptionInvoice,
    SubscriptionPayment,
    SubscriptionPlan,
    User,
)
from .entitlements import active_overrides, current_subscription, default_plan
from .pricing import get_setting, price_in_force, pricing_audit

METHODS = ("CASH", "BANK_TRANSFER", "MOBILE_MONEY")
PLAN_PAUSE_REASON = "Your current plan does not include a Marketplace listing"


def add_months(value: datetime, months: int) -> datetime:
    index = value.month - 1 + months
    year, month = value.year + index // 12, index % 12 + 1
    return value.replace(year=year, month=month, day=min(value.day, monthrange(year, month)[1]))


def period_end(start: datetime, interval: str) -> datetime:
    return add_months(start, 12 if interval == "ANNUAL" else 1)


def notify_owner(db: Session, business: Business, kind: str, ref: str, **data) -> None:
    """In-app notice for the laundry owner; one per (kind, ref) so repeated billing runs never spam."""
    marker = f'"ref": "{kind}:{ref}"'
    if db.scalar(select(Notification.id).where(Notification.user_id == business.owner_id, Notification.kind == kind,
                                               Notification.data_json.contains(marker))):
        return
    db.add(Notification(user_id=business.owner_id, kind=kind, data_json=json.dumps({"ref": f"{kind}:{ref}", **data})))


class BillingService:
    def __init__(self, db: Session):
        self.db = db

    # ---- pricing for one business ---------------------------------------------------------------------------------
    def list_price(self, plan: SubscriptionPlan, interval: str, at: datetime) -> int:
        price = price_in_force(self.db, plan.id, interval, at)
        if price is None:
            raise AppError(409, "PLAN_NOT_PRICED", f"{plan.name} has no {interval.lower()} price")
        return price.amount

    def terms(self, business_id: str, plan: SubscriptionPlan, interval: str, at: datetime) -> tuple[int, list[dict]]:
        """List price and the discount lines this business's terms give for one period starting at `at`."""
        listed = self.list_price(plan, interval, at)
        lines: list[dict] = []
        for o in active_overrides(self.db, business_id, at, ("COMPLIMENTARY_PLAN", "PLAN_PRICE", "PLAN_DISCOUNT")):
            if o.plan_id != plan.id:
                continue
            if o.type == "COMPLIMENTARY_PLAN":
                lines = [{"kind": "DISCOUNT", "description": f"Complimentary — {o.reason}", "amount": -listed,
                          "override_id": o.id}]
                break
            if o.type == "PLAN_PRICE":
                special = int(o.value) * (12 if interval == "ANNUAL" else 1)
                if special < listed:
                    lines.append({"kind": "DISCOUNT", "description": f"Special price — {o.reason}",
                                  "amount": special - listed, "override_id": o.id})
            if o.type == "PLAN_DISCOUNT":
                lines.append({"kind": "DISCOUNT", "description": f"{o.value.normalize()} % off — {o.reason}",
                              "amount": -percentage_of(listed, o.value), "override_id": o.id})
        if len(lines) > 1:  # never stack price terms: keep the best one for the provider
            lines = [min(lines, key=lambda x: x["amount"])]
        return listed, lines

    def quote(self, business_id: str, plan: SubscriptionPlan, interval: str, at: datetime | None = None) -> dict:
        at = at or now_utc()
        listed, lines = self.terms(business_id, plan, interval, at)
        return {"list_price": listed, "discount": -sum(x["amount"] for x in lines), "price": listed + sum(x["amount"] for x in lines),
                "terms": [x["description"] for x in lines]}

    # ---- invoices -------------------------------------------------------------------------------------------------
    def issue_invoice(self, sub: BusinessSubscription, start: datetime, end: datetime, credit: int = 0,
                      credit_note: str = "") -> SubscriptionInvoice | None:
        existing = self.db.scalar(select(SubscriptionInvoice).where(SubscriptionInvoice.subscription_id == sub.id,
                                                                    SubscriptionInvoice.period_start == start))
        if existing:
            return existing
        plan = self.db.get(SubscriptionPlan, sub.plan_id)
        business = self.db.get(Business, sub.business_id)
        listed, discounts = self.terms(sub.business_id, plan, sub.interval, start)
        lines = [{"kind": "PLAN", "description": f"{plan.name} — {sub.interval.lower()}", "amount": listed}]
        fee = get_setting(self.db, "marketplace_listing_fee") or 0
        account = self.db.scalar(select(MarketplaceAccount).where(MarketplaceAccount.business_id == sub.business_id))
        if fee and account and account.status == "ACTIVE":
            lines.append({"kind": "MARKETPLACE_FEE", "description": "Marketplace listing",
                          "amount": fee * (12 if sub.interval == "ANNUAL" else 1)})
        lines += discounts
        subtotal = sum(x["amount"] for x in lines if x["amount"] > 0)
        if subtotal == 0:
            sub.price_amount = 0
            return None  # free: nothing to invoice
        after_terms = max(subtotal + sum(x["amount"] for x in lines if x["amount"] < 0), 0)
        if credit:
            credit = min(credit, after_terms)
            lines.append({"kind": "CREDIT", "description": credit_note or "Credit", "amount": -credit})
        discount = subtotal - max(subtotal + sum(x["amount"] for x in lines if x["amount"] < 0), 0)
        number = f"INV-{start.year}-{self.db.scalar(text('SELECT nextval(\'invoice_number_seq\')')):06d}"
        invoice = SubscriptionInvoice(number=number, business_id=sub.business_id, subscription_id=sub.id, period_start=start,
                                      period_end=end, subtotal=subtotal, discount=discount, amount_due=subtotal - discount,
                                      status="OPEN", issued_at=now_utc(),
                                      due_at=start + timedelta(days=get_setting(self.db, "invoice_payment_terms_days") or 7))
        for position, line in enumerate(lines):
            invoice.lines.append(InvoiceLine(kind=line["kind"], description=line["description"][:200], amount=line["amount"],
                                             position=position))
        if invoice.amount_due == 0:
            invoice.status, invoice.paid_at = "PAID", invoice.issued_at
        try:
            with self.db.begin_nested():
                self.db.add(invoice)
                self.db.flush()
        except IntegrityError:
            return self.db.scalar(select(SubscriptionInvoice).where(SubscriptionInvoice.subscription_id == sub.id,
                                                                    SubscriptionInvoice.period_start == start))
        sub.price_amount = after_terms  # the recurring price (excludes one-off credits)
        if invoice.amount_due:
            notify_owner(self.db, business, "INVOICE_ISSUED", invoice.id, number=invoice.number, amount=invoice.amount_due)
        return invoice

    # ---- subscribing ----------------------------------------------------------------------------------------------
    def _start(self, business: Business, plan: SubscriptionPlan, interval: str, at: datetime, source: str,
               allow_trial: bool, credit: int = 0, credit_note: str = "") -> BusinessSubscription:
        listed = self.list_price(plan, interval, at)
        trialled = self.db.scalar(select(BusinessSubscription.id).where(BusinessSubscription.business_id == business.id,
                                                                        BusinessSubscription.plan_id == plan.id))
        sub = BusinessSubscription(business_id=business.id, plan_id=plan.id, interval=interval, source=source,
                                   current_period_start=at, current_period_end=period_end(at, interval), status="ACTIVE")
        if listed > 0 and allow_trial and plan.trial_days and not trialled:
            sub.status, sub.trial_ends_at = "TRIALING", at + timedelta(days=plan.trial_days)
            sub.current_period_end = sub.trial_ends_at
        self.db.add(sub)
        self.db.flush()
        if sub.status == "TRIALING":
            sub.price_amount = self.quote(business.id, plan, interval, at)["price"]
        else:
            self.issue_invoice(sub, at, sub.current_period_end, credit, credit_note)
        return sub

    def unused_credit(self, sub: BusinessSubscription, at: datetime) -> int:
        """Money paid for time not yet used: the rest of the current period plus any paid future period."""
        credit = 0
        for paid in self.db.scalars(select(SubscriptionInvoice).where(
                SubscriptionInvoice.subscription_id == sub.id, SubscriptionInvoice.amount_paid > 0,
                SubscriptionInvoice.status != "VOID", SubscriptionInvoice.period_end > at)):
            start, end = as_utc(paid.period_start), as_utc(paid.period_end)
            unused = (end - max(at, start)).total_seconds() / (end - start).total_seconds()
            credit += int(paid.amount_paid * min(unused, 1))
        return credit

    def change_plan(self, business: Business, plan: SubscriptionPlan, interval: str, actor: User, source: str = "SELF",
                    reason: str = "") -> BusinessSubscription:
        at = now_utc()
        if plan.status == "RETIRED" or (plan.status == "HIDDEN" and source == "SELF"):
            raise AppError(409, "PLAN_UNAVAILABLE", "This plan is not available")
        current = current_subscription(self.db, business.id)
        current_plan = self.db.get(SubscriptionPlan, current.plan_id) if current else default_plan(self.db)
        if current and current.plan_id == plan.id and current.interval == interval and not current.cancel_at_period_end:
            raise AppError(409, "ALREADY_ON_PLAN", "You are already on this plan")
        downgrade = plan.sort_order < current_plan.sort_order
        if current and downgrade and current.status in ("ACTIVE", "PAST_DUE") and current.price_amount > 0 and source == "SELF":
            current.next_plan_id, current.cancel_at_period_end = plan.id, False
            self._log(actor, "SUBSCRIPTION_DOWNGRADE_SCHEDULED", current, {"to": plan.code}, reason)
            self.db.commit()
            return current
        credit, note = 0, ""
        # Trials are for laundries not yet paying; a paying customer who upgrades is invoiced at once with a credit.
        paying = bool(current and current.status in ("ACTIVE", "PAST_DUE") and current.price_amount > 0)
        if current:
            credit = self.unused_credit(current, at)
            note = f"Unused time on {current_plan.name}"
            self._end(current, at, "CANCELLED")
        sub = self._start(business, plan, interval, at, source, allow_trial=not paying, credit=credit, credit_note=note)
        self._log(actor, "SUBSCRIPTION_CHANGED", sub, {"from": current_plan.code, "to": plan.code, "interval": interval}, reason)
        self.db.commit()
        return sub

    def cancel(self, business: Business, actor: User) -> BusinessSubscription:
        sub = current_subscription(self.db, business.id)
        if not sub or sub.price_amount == 0 and sub.status != "TRIALING":
            raise AppError(409, "NOTHING_TO_CANCEL", "You are on the free plan")
        if sub.status == "TRIALING":
            self._end(sub, now_utc(), "CANCELLED")
        else:
            sub.cancel_at_period_end, sub.next_plan_id = True, None
        self._log(actor, "SUBSCRIPTION_CANCELLED", sub, {"at_period_end": sub.ended_at is None}, "")
        self.db.commit()
        return sub

    def _end(self, sub: BusinessSubscription, at: datetime, status: str) -> None:
        sub.status, sub.ended_at = status, at
        for invoice in self.db.scalars(select(SubscriptionInvoice).where(SubscriptionInvoice.subscription_id == sub.id,
                                                                        SubscriptionInvoice.status == "OPEN")):
            if invoice.amount_paid == 0:
                invoice.status, invoice.void_reason = "VOID", f"Subscription {status.lower()}"
        self.db.flush()

    def _log(self, actor: User | None, action: str, sub: BusinessSubscription, after: dict, reason: str) -> None:
        pricing_audit(self.db, actor, action, "subscription", sub.id, None, after, reason, sub.business_id)

    # ---- payments -------------------------------------------------------------------------------------------------
    def record_payment(self, invoice: SubscriptionInvoice, amount: int, method: str, reference: str | None,
                       received_at: datetime | None, actor: User, idempotency_key: str | None, note: str = "") -> SubscriptionPayment:
        if idempotency_key:
            existing = self.db.scalar(select(SubscriptionPayment).where(SubscriptionPayment.idempotency_key == idempotency_key))
            if existing:
                if existing.invoice_id != invoice.id or existing.amount != amount:
                    raise AppError(409, "IDEMPOTENCY_CONFLICT", "This key was used for a different payment")
                return existing
        if method not in METHODS:
            raise AppError(422, "INVALID_METHOD", "Method must be cash, bank transfer or mobile money")
        if invoice.status != "OPEN":
            raise AppError(409, "INVOICE_NOT_OPEN", f"This invoice is {invoice.status.lower()}")
        remaining = invoice.amount_due - invoice.amount_paid
        if amount <= 0 or amount > remaining:
            raise AppError(422, "INVALID_AMOUNT", f"Amount must be between 1 and {remaining:,}", {"remaining": remaining})
        if reference and self.db.scalar(select(SubscriptionPayment.id).where(SubscriptionPayment.reference == reference)):
            raise AppError(409, "DUPLICATE_REFERENCE", "This reference was already recorded")
        received = as_utc(received_at) if received_at else now_utc()
        if received > now_utc() + timedelta(minutes=5):
            raise AppError(422, "FUTURE_PAYMENT", "A payment cannot be received in the future")
        payment = SubscriptionPayment(invoice_id=invoice.id, business_id=invoice.business_id, amount=amount, method=method,
                                      channel="MANUAL", reference=reference or None, idempotency_key=idempotency_key,
                                      received_at=received, recorded_by=actor.id, note=note)
        self.db.add(payment)
        invoice.amount_paid += amount
        if invoice.amount_paid >= invoice.amount_due:
            invoice.status, invoice.paid_at = "PAID", received
            sub = self.db.get(BusinessSubscription, invoice.subscription_id)
            if sub.status == "PAST_DUE" and not self._overdue(sub, now_utc()):
                sub.status = "ACTIVE"
            notify_owner(self.db, self.db.get(Business, invoice.business_id), "INVOICE_PAID", invoice.id,
                         number=invoice.number, amount=invoice.amount_due)
        self.db.flush()
        pricing_audit(self.db, actor, "SUBSCRIPTION_PAYMENT_RECORDED", "invoice", invoice.id, None,
                      {"amount": amount, "method": method, "reference": reference, "received_at": received.isoformat()},
                      note, invoice.business_id)
        self.db.commit()
        return payment

    def void_invoice(self, invoice: SubscriptionInvoice, actor: User, reason: str) -> SubscriptionInvoice:
        if invoice.status != "OPEN" or invoice.amount_paid:
            raise AppError(409, "CANNOT_VOID", "Only unpaid open invoices can be voided")
        invoice.status, invoice.void_reason = "VOID", reason
        pricing_audit(self.db, actor, "INVOICE_VOIDED", "invoice", invoice.id, {"status": "OPEN"}, {"status": "VOID"}, reason,
                      invoice.business_id)
        self.db.commit()
        return invoice

    def _overdue(self, sub: BusinessSubscription, at: datetime) -> SubscriptionInvoice | None:
        return self.db.scalar(select(SubscriptionInvoice).where(
            SubscriptionInvoice.subscription_id == sub.id, SubscriptionInvoice.status == "OPEN",
            SubscriptionInvoice.due_at < at).order_by(SubscriptionInvoice.due_at))

    # ---- the cycle ------------------------------------------------------------------------------------------------
    def run(self, at: datetime | None = None) -> dict:
        """Idempotent. Safe to run as often as you like (the API runs it on a timer; admins can trigger it)."""
        at = at or now_utc()
        stats = {"trials_converted": 0, "renewed": 0, "invoices": 0, "past_due": 0, "expired": 0, "ended": 0,
                 "pilots_ended": 0, "reminders": 0}
        remind = timedelta(days=get_setting(self.db, "trial_reminder_days") or 7)
        for sub in list(self.db.scalars(select(BusinessSubscription).where(BusinessSubscription.ended_at.is_(None)))):
            business = self.db.get(Business, sub.business_id)
            plan = self.db.get(SubscriptionPlan, sub.plan_id)
            if sub.status == "TRIALING":
                ends = as_utc(sub.trial_ends_at)
                if ends - remind <= at < ends:
                    notify_owner(self.db, business, "TRIAL_ENDING", sub.id, plan=plan.name, ends_at=ends.isoformat())
                    stats["reminders"] += 1
                if ends <= at:
                    sub.status = "ACTIVE"
                    sub.current_period_start, sub.current_period_end = ends, period_end(ends, sub.interval)
                    if self.issue_invoice(sub, ends, sub.current_period_end):
                        stats["invoices"] += 1
                    notify_owner(self.db, business, "TRIAL_ENDED", sub.id, plan=plan.name)
                    stats["trials_converted"] += 1
            guard = 0
            while sub.ended_at is None and sub.status in ("ACTIVE", "PAST_DUE") and as_utc(sub.current_period_end) <= at and guard < 36:
                guard += 1
                end = as_utc(sub.current_period_end)
                if sub.cancel_at_period_end:
                    self._end(sub, end, "CANCELLED")
                    notify_owner(self.db, business, "SUBSCRIPTION_ENDED", sub.id, plan=plan.name)
                    stats["ended"] += 1
                elif sub.next_plan_id:
                    nxt = self.db.get(SubscriptionPlan, sub.next_plan_id)
                    self._end(sub, end, "CANCELLED")
                    self._start(business, nxt, sub.interval, end, "SELF", allow_trial=False)
                    stats["ended"] += 1
                else:
                    sub.current_period_start, sub.current_period_end = end, period_end(end, sub.interval)
                    if self.issue_invoice(sub, end, sub.current_period_end):
                        stats["invoices"] += 1
                    stats["renewed"] += 1
            if sub.ended_at is None and sub.status in ("ACTIVE", "PAST_DUE"):
                overdue = self._overdue(sub, at)
                if overdue and as_utc(overdue.due_at) + timedelta(days=plan.grace_days) <= at:
                    self._end(sub, at, "EXPIRED")
                    notify_owner(self.db, business, "SUBSCRIPTION_EXPIRED", sub.id, plan=plan.name, invoice=overdue.number)
                    stats["expired"] += 1
                elif overdue and sub.status == "ACTIVE":
                    sub.status = "PAST_DUE"
                    notify_owner(self.db, business, "INVOICE_OVERDUE", overdue.id, number=overdue.number)
                    stats["past_due"] += 1
        stats["pilots_ended"], reminders = self._pilots(at, remind)
        stats["reminders"] += reminders
        stats["marketplace_paused"], stats["marketplace_restored"] = self._marketplace_eligibility(at)
        self.db.commit()
        return stats

    def _marketplace_eligibility(self, at: datetime) -> tuple[int, int]:
        """Listings follow plan eligibility automatically. Only pauses made by this rule are undone by it;
        suspensions decided by an administrator are never lifted here."""
        from .entitlements import resolve

        paused = restored = 0
        for account in list(self.db.scalars(select(MarketplaceAccount).where(MarketplaceAccount.status.in_(("ACTIVE", "SUSPENDED"))))):
            eligible = "marketplace_eligible" in resolve(self.db, account.business_id, at).features
            business = self.db.get(Business, account.business_id)
            if account.status == "ACTIVE" and not eligible:
                account.status, account.rejection_reason = "SUSPENDED", PLAN_PAUSE_REASON
                notify_owner(self.db, business, "MARKETPLACE_PAUSED", f"{account.id}:{at.date()}")
                paused += 1
            elif account.status == "SUSPENDED" and account.rejection_reason == PLAN_PAUSE_REASON and eligible:
                account.status, account.rejection_reason = "ACTIVE", None
                notify_owner(self.db, business, "MARKETPLACE_RESTORED", f"{account.id}:{at.date()}")
                restored += 1
        return paused, restored

    def _pilots(self, at: datetime, remind: timedelta) -> tuple[int, int]:
        ended = reminders = 0
        for enrollment in list(self.db.scalars(select(PilotEnrollment).where(PilotEnrollment.status == "ACTIVE"))):
            program = self.db.get(PilotProgram, enrollment.program_id)
            business = self.db.get(Business, enrollment.business_id)
            plan = self.db.get(SubscriptionPlan, program.plan_id)
            ends = as_utc(enrollment.ends_at)
            if ends - remind <= at < ends:
                policy = "PILOT_ENDING_INVOICE" if program.transition_policy == "INVOICE" else "PILOT_ENDING_DOWNGRADE"
                notify_owner(self.db, business, policy, enrollment.id, plan=plan.name, ends_at=ends.isoformat())
                reminders += 1
            if ends > at:
                continue
            enrollment.status, enrollment.transitioned_at = "ENDED", at
            current = current_subscription(self.db, business.id)
            if program.transition_policy == "INVOICE" and not (current and current.plan_id == plan.id):
                # Offer the plan: an invoice is issued, nothing is charged; unpaid after grace → default plan.
                if current:
                    self._end(current, ends, "CANCELLED")
                self._start(business, plan, "MONTHLY", ends, "ADMIN", allow_trial=False)
            notify_owner(self.db, business, "PILOT_ENDED", enrollment.id, plan=plan.name, policy=program.transition_policy)
            ended += 1
        return ended, reminders

    # ---- views ----------------------------------------------------------------------------------------------------
    def invoice_out(self, invoice: SubscriptionInvoice, with_lines: bool = True) -> dict:
        data = {"id": invoice.id, "number": invoice.number, "business_id": invoice.business_id,
                "period_start": invoice.period_start, "period_end": invoice.period_end, "subtotal": invoice.subtotal,
                "discount": invoice.discount, "amount_due": invoice.amount_due, "amount_paid": invoice.amount_paid,
                "balance": invoice.amount_due - invoice.amount_paid, "status": invoice.status, "issued_at": invoice.issued_at,
                "due_at": invoice.due_at, "paid_at": invoice.paid_at, "void_reason": invoice.void_reason}
        if with_lines:
            data["lines"] = [{"kind": x.kind, "description": x.description, "amount": x.amount} for x in invoice.lines]
            data["payments"] = [{"id": p.id, "amount": p.amount, "method": p.method, "reference": p.reference,
                                 "received_at": p.received_at, "channel": p.channel} for p in self.db.scalars(
                select(SubscriptionPayment).where(SubscriptionPayment.invoice_id == invoice.id).order_by(SubscriptionPayment.received_at))]
        return data

    def revenue(self, start: datetime, end: datetime) -> dict:
        db = self.db
        live = Order.status.notin_([S.CANCELLED, S.REJECTED])
        subs = list(db.scalars(select(BusinessSubscription).where(BusinessSubscription.ended_at.is_(None))))
        mrr = sum(s.price_amount // (12 if s.interval == "ANNUAL" else 1) for s in subs
                  if s.status in ("ACTIVE", "PAST_DUE") and s.price_amount > 0)
        complimentary = {o.business_id for o in db.scalars(select(CommercialOverride).where(
            CommercialOverride.type == "COMPLIMENTARY_PLAN", CommercialOverride.revoked_at.is_(None),
            CommercialOverride.effective_from <= now_utc(),
            (CommercialOverride.expires_at.is_(None)) | (CommercialOverride.expires_at > now_utc())))}
        issued = db.execute(select(func.count(), func.coalesce(func.sum(SubscriptionInvoice.amount_due), 0)).where(
            SubscriptionInvoice.issued_at >= start, SubscriptionInvoice.issued_at < end,
            SubscriptionInvoice.status != "VOID")).one()
        collected = db.scalar(select(func.coalesce(func.sum(SubscriptionPayment.amount), 0)).where(
            SubscriptionPayment.received_at >= start, SubscriptionPayment.received_at < end)) or 0
        outstanding = db.execute(select(func.count(), func.coalesce(func.sum(SubscriptionInvoice.amount_due -
                                 SubscriptionInvoice.amount_paid), 0)).where(SubscriptionInvoice.status == "OPEN")).one()
        gmv = db.scalar(select(func.coalesce(func.sum(Order.total), 0)).where(
            Order.source == "MARKETPLACE", live, Order.created_at >= start, Order.created_at < end)) or 0
        earned = db.scalar(select(func.coalesce(func.sum(Commission.amount), 0)).where(
            Commission.entry_type == "EARNED", Commission.created_at >= start, Commission.created_at < end)) or 0
        reversed_ = -(db.scalar(select(func.coalesce(func.sum(Commission.amount), 0)).where(
            Commission.entry_type == "REVERSED", Commission.created_at >= start, Commission.created_at < end)) or 0)
        by_business = [
            {"business_id": bid, "name": name, "orders": orders, "gmv": int(gmv_b), "earned": int(e or 0),
             "reversed": int(r or 0), "net": int((e or 0) - (r or 0))}
            for bid, name, orders, gmv_b, e, r in db.execute(
                select(Business.id, Business.name,
                       select(func.count()).where(Order.business_id == Business.id, Order.source == "MARKETPLACE", live,
                                                  Order.created_at >= start, Order.created_at < end).scalar_subquery(),
                       select(func.coalesce(func.sum(Order.total), 0)).where(
                           Order.business_id == Business.id, Order.source == "MARKETPLACE", live, Order.created_at >= start,
                           Order.created_at < end).scalar_subquery(),
                       select(func.sum(Commission.amount)).where(Commission.business_id == Business.id,
                                                                 Commission.entry_type == "EARNED", Commission.created_at >= start,
                                                                 Commission.created_at < end).scalar_subquery(),
                       select(-func.sum(Commission.amount)).where(Commission.business_id == Business.id,
                                                                  Commission.entry_type == "REVERSED", Commission.created_at >= start,
                                                                  Commission.created_at < end).scalar_subquery()))
            .all() if orders or e or r]
        # Reconciliation: invoice balances must equal the payments recorded against them.
        paid_on_invoices = db.scalar(select(func.coalesce(func.sum(SubscriptionInvoice.amount_paid), 0))) or 0
        all_payments = db.scalar(select(func.coalesce(func.sum(SubscriptionPayment.amount), 0))) or 0
        ledger_total = db.scalar(select(func.coalesce(func.sum(Commission.amount), 0))) or 0
        return {
            "subscriptions": {
                "mrr": mrr, "active_paid": sum(1 for s in subs if s.status in ("ACTIVE", "PAST_DUE") and s.price_amount > 0),
                "past_due": sum(1 for s in subs if s.status == "PAST_DUE"),
                "trialing": sum(1 for s in subs if s.status == "TRIALING"), "complimentary": len(complimentary),
                "expired_in_period": db.scalar(select(func.count()).where(BusinessSubscription.status == "EXPIRED",
                                               BusinessSubscription.ended_at >= start, BusinessSubscription.ended_at < end)) or 0,
                "invoiced": int(issued[1]), "invoices_issued": issued[0], "collected": int(collected),
                "outstanding": int(outstanding[1]), "outstanding_invoices": outstanding[0]},
            "marketplace": {"gmv": int(gmv), "commission_earned": int(earned), "commission_reversed": int(reversed_),
                            "commission_net": int(earned - reversed_), "by_business": sorted(by_business, key=lambda x: -x["net"])},
            # Two separate revenue streams; neither includes the other.
            "platform_revenue": {"subscription_collections": int(collected), "marketplace_commission_net": int(earned - reversed_),
                                 "total": int(collected + earned - reversed_)},
            "reconciliation": {"invoice_payments": int(paid_on_invoices), "payments_recorded": int(all_payments),
                               "matches": int(paid_on_invoices) == int(all_payments), "commission_ledger_net": int(ledger_total)},
        }


def business_or_404(db: Session, business_id: str) -> Business:
    business = db.get(Business, business_id)
    if not business:
        raise not_found("Business")
    return business
