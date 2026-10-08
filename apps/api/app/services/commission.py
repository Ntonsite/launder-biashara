"""The one place Marketplace commission is decided and calculated.

When is commission earned?  When a Marketplace order is COMPLETED (completion already requires full payment).
Which terms apply?          The rule in force when the order was *placed* (snapshotted on the order), so later rule
                            changes never re-price an order. Precedence at placement: this laundry's promotion >
                            this laundry's rate > a promotion for all laundries > the default.
Trials?                     A Marketplace trial is a promotion for one laundry tied to its agreement. A trial never
                            makes a laundry pay more than it would without it: while a trial runs, the lower of the
                            trial rate and the laundry's standard rate (its own rate, else a promotion for all, else
                            the default) applies. So a special rate never takes away a promised trial, and a trial
                            never takes away a better special rate. Admins cannot add another promotion for the
                            laundry over a trial's dates.
What is the basis?          The laundry services subtotal, less discounts unless the rule says otherwise, plus the pickup
                            fee only if the rule includes it. A minimum commission never exceeds the basis.
Refunds?                    Refunding a completed order's payment writes one REVERSED entry for the full earned amount.
                            Entries are never edited; (order, entry type) is unique, so retries cannot double count.
Cancellations?              Orders cannot be cancelled after completion, and nothing is earned before it.
Walk-in, phone, WhatsApp?   Never: only source = MARKETPLACE is eligible.
"""
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.errors import AppError
from ..domain.clock import now_utc
from ..domain.money import percentage_of
from ..models import Commission, CommissionRule, MarketplaceAgreement, Order

ELIGIBLE_SOURCES = {"MARKETPLACE"}


@dataclass
class Calculation:
    rule_id: str
    rate: Decimal
    basis: int
    amount: int
    detail: dict
    waived: int = 0
    agreement_id: str | None = None

    @property
    def laundry_amount(self) -> int:
        return self.basis - self.amount


def _in_force(at: datetime):
    return and_(CommissionRule.effective_from <= at,
                or_(CommissionRule.effective_to.is_(None), CommissionRule.effective_to > at))


class CommissionService:
    def __init__(self, db: Session):
        self.db = db

    def rule_for(self, business_id: str, at: datetime | None = None, include_trials: bool = True) -> CommissionRule:
        at = at or now_utc()
        candidates = [
            (CommissionRule.scope == "PROMOTION", CommissionRule.business_id == business_id),
            (CommissionRule.scope == "BUSINESS", CommissionRule.business_id == business_id),
            (CommissionRule.scope == "PROMOTION", CommissionRule.business_id.is_(None)),
            (CommissionRule.scope == "DEFAULT", CommissionRule.business_id.is_(None)),
        ]
        for scope, owner in candidates:
            stmt = select(CommissionRule).where(scope, owner, _in_force(at))
            if not include_trials:
                stmt = stmt.where(CommissionRule.agreement_id.is_(None))
            rule = self.db.scalar(stmt.order_by(CommissionRule.effective_from.desc()))
            if rule and rule.agreement_id:
                standard = self.rule_for(business_id, at, include_trials=False)
                return standard if Decimal(standard.rate) < Decimal(rule.rate) else rule
            if rule:
                return rule
        raise AppError(500, "NO_COMMISSION_RULE", "No default Marketplace commission is configured")

    @staticmethod
    def calculate(rule: CommissionRule, subtotal: int, discount: int = 0, pickup_fee: int = 0) -> Calculation:
        basis = subtotal - (discount if rule.discounts_reduce_basis else 0) + (pickup_fee if rule.include_pickup_fee else 0)
        basis = max(basis, 0)
        amount = percentage_of(basis, Decimal(rule.rate))
        minimum_applied = False
        if rule.min_commission and amount < rule.min_commission:
            amount, minimum_applied = min(rule.min_commission, basis), True
        return Calculation(rule.id, Decimal(rule.rate), basis, amount, {
            "services_subtotal": subtotal, "discount": discount, "discount_reduces_basis": rule.discounts_reduce_basis,
            "pickup_fee": pickup_fee, "pickup_fee_included": rule.include_pickup_fee, "rate": str(rule.rate),
            "minimum": rule.min_commission, "minimum_applied": minimum_applied, "scope": rule.scope})

    def snapshot(self, order: Order) -> None:
        """Called when a Marketplace order is placed: fixes the terms it will be charged under."""
        if order.source not in ELIGIBLE_SOURCES:
            return
        at = order.created_at or now_utc()
        rule = self.rule_for(order.business_id, at)
        standard = rule if not rule.agreement_id else self.rule_for(order.business_id, at, include_trials=False)
        order.commission_rule_id, order.commission_rate = rule.id, Decimal(rule.rate)
        order.commission_standard_rate = Decimal(standard.rate)
        order.marketplace_agreement_id = self.db.scalar(select(MarketplaceAgreement.id).where(
            MarketplaceAgreement.business_id == order.business_id, MarketplaceAgreement.status == "ACTIVE"))

    def preview(self, order: Order) -> Calculation | None:
        if order.source not in ELIGIBLE_SOURCES:
            return None
        rule = self.db.get(CommissionRule, order.commission_rule_id) if order.commission_rule_id else None
        rule = rule or self.rule_for(order.business_id, order.created_at)
        calc = self.calculate(rule, order.subtotal, order.discount, order.delivery_fee)
        if rule.agreement_id and order.commission_standard_rate is not None:
            # Waived = the standard rate on the same basis, minus what the trial charges.
            calc.waived = max(percentage_of(calc.basis, Decimal(order.commission_standard_rate)) - calc.amount, 0)
            calc.agreement_id = rule.agreement_id
            calc.detail = {**calc.detail, "trial": True, "standard_rate": str(order.commission_standard_rate),
                           "waived": calc.waived}
        return calc

    def earn(self, order: Order) -> Commission | None:
        calc = self.preview(order)
        if calc is None:
            return None
        if self.db.scalar(select(Commission.id).where(Commission.order_id == order.id, Commission.entry_type == "EARNED")):
            return None  # idempotent
        entry = Commission(order_id=order.id, business_id=order.business_id, entry_type="EARNED", rule_id=calc.rule_id,
                           rate=calc.rate, base_amount=calc.basis, amount=calc.amount, basis_json=json.dumps(calc.detail),
                           waived_amount=calc.waived, agreement_id=calc.agreement_id or order.marketplace_agreement_id,
                           status="ACCRUED")
        return self._add(entry)

    def reverse(self, order: Order, reason: str) -> Commission | None:
        earned = self.db.scalar(select(Commission).where(Commission.order_id == order.id, Commission.entry_type == "EARNED"))
        if not earned:
            return None
        if self.db.scalar(select(Commission.id).where(Commission.order_id == order.id, Commission.entry_type == "REVERSED")):
            return None
        entry = Commission(order_id=order.id, business_id=order.business_id, entry_type="REVERSED", rule_id=earned.rule_id,
                           rate=earned.rate, base_amount=earned.base_amount, amount=-earned.amount, status="REVERSED",
                           waived_amount=-earned.waived_amount, agreement_id=earned.agreement_id,
                           basis_json=json.dumps({"reverses": earned.id, "reason": reason}))
        return self._add(entry)

    def _add(self, entry: Commission) -> Commission | None:
        try:
            with self.db.begin_nested():
                self.db.add(entry)
                self.db.flush()
        except IntegrityError:
            return None  # a concurrent request wrote the same entry; the unique key keeps one
        return entry


def commission_terms(rule: CommissionRule) -> dict:
    """Provider-facing description of the terms (no internal codes)."""
    return {"rate": float(rule.rate), "minimum": rule.min_commission, "includes_pickup_fee": rule.include_pickup_fee,
            "discounts_reduce_basis": rule.discounts_reduce_basis,
            "kind": "trial" if rule.agreement_id else rule.scope.lower(),
            "until": rule.effective_to.isoformat() if rule.effective_to else None}
