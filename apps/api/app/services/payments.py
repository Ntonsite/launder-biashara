"""Payments. Phase 1 supports CASH (recorded by the laundry) and MOBILE_MONEY through a provider abstraction.

Only the `sandbox` provider exists today. It never moves money: initiating puts the payment in PROCESSING and the
outcome arrives through the signed webhook, exactly as a real aggregator callback would. In development the outcome can
be triggered through /api/v1/dev/payments/{reference}/simulate, which is disabled in production.
"""
import hashlib
import hmac
import secrets
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.errors import AppError
from ..domain.clock import now_utc
from ..models import Order, Payment
from .audit import audit
from .notifications import notify_order


def balance(order: Order) -> int:
    return max(order.total - (order.amount_paid or 0), 0)


PAYMENT_TRANSITIONS = {
    "PENDING": {"PROCESSING", "PAID", "FAILED"},
    "PROCESSING": {"PAID", "FAILED"},
    "FAILED": {"PROCESSING", "PAID"},
    "PAID": {"REFUNDED"},
    "REFUNDED": set(),
}


class MobileMoneyProvider(Protocol):
    name: str

    def initiate(self, payment: Payment, phone: str) -> str: ...


class SandboxProvider:
    name = "sandbox"

    def initiate(self, payment: Payment, phone: str) -> str:
        return f"SBX-{secrets.token_hex(8).upper()}"


def provider() -> MobileMoneyProvider:
    return SandboxProvider()


def sign(body: bytes) -> str:
    return hmac.new(settings.payment_webhook_secret.encode(), body, hashlib.sha256).hexdigest()


def verify_signature(body: bytes, signature: str | None) -> bool:
    return bool(signature) and hmac.compare_digest(sign(body), signature)


def payment_out(p: Payment | None) -> dict | None:
    if not p:
        return None
    return {"id": p.id, "method": p.method, "status": p.status, "amount": p.amount, "provider": p.provider,
            "reference": p.provider_reference, "failure_reason": p.failure_reason, "updated_at": p.updated_at}


class PaymentService:
    def __init__(self, db: Session):
        self.db = db

    def latest(self, order_id: str) -> Payment | None:
        return self.db.scalar(select(Payment).where(Payment.order_id == order_id).order_by(Payment.created_at.desc()))

    def _move(self, payment: Payment, order: Order, target: str, actor_id: str | None, reason: str | None = None) -> None:
        if target not in PAYMENT_TRANSITIONS[payment.status]:
            raise AppError(409, "INVALID_PAYMENT_STATE", f"Payment cannot move from {payment.status} to {target}")
        payment.status = target
        payment.failure_reason = reason if target == "FAILED" else None
        payment.updated_at = now_utc()
        order.payment_status = target
        if target == "PAID":
            payment.paid_at = payment.updated_at
            order.amount_paid = (order.amount_paid or 0) + payment.amount
            order.payment_status = "PAID" if order.amount_paid >= order.total else "PARTIAL"
        elif target == "REFUNDED":
            payment.refunded_at = payment.updated_at
            order.amount_paid = max((order.amount_paid or 0) - payment.amount, 0)
        elif target == "FAILED" and order.amount_paid:
            order.payment_status = "PARTIAL"  # an earlier part payment still stands
        audit(self.db, actor_id, f"PAYMENT_{target}", "payment", payment.id, order_id=order.id, amount=payment.amount)
        if target in ("PAID", "FAILED", "REFUNDED"):
            notify_order(self.db, order, f"PAYMENT_{target}")

    def start_mobile_money(self, order: Order, phone: str, actor_id: str) -> Payment:
        if order.status in ("CANCELLED", "REJECTED"):
            raise AppError(409, "ORDER_CLOSED", "This order is no longer active")
        payment = self.latest(order.id)
        if payment and payment.status == "PROCESSING":
            return payment  # idempotent: a request is already waiting for the customer's approval
        if balance(order) <= 0 or order.payment_status == "REFUNDED":
            raise AppError(409, "ALREADY_PAID", "This order has already been paid")
        if payment is None or payment.method != "MOBILE_MONEY" or payment.status in ("PAID", "REFUNDED"):
            payment = Payment(order_id=order.id, method="MOBILE_MONEY", amount=balance(order), status="PENDING")
            self.db.add(payment)
            self.db.flush()
            order.payment_method = "MOBILE_MONEY"
        gateway = provider()
        payment.provider, payment.payer_phone = gateway.name, phone
        payment.provider_reference = gateway.initiate(payment, phone)
        self._move(payment, order, "PROCESSING", actor_id)
        self.db.commit()
        return payment

    def apply_provider_result(self, reference: str, outcome: str, reason: str | None) -> Payment:
        payment = self.db.scalar(select(Payment).where(Payment.provider_reference == reference))
        if not payment:
            raise AppError(404, "NOT_FOUND", "Payment not found")
        if payment.status == outcome:
            return payment  # providers retry callbacks; repeated delivery is a no-op
        order = self.db.get(Order, payment.order_id)
        self._move(payment, order, outcome, None, reason or None)
        self.db.commit()
        return payment

    def record_cash(self, order: Order, actor_id: str) -> Payment:
        return self.record_manual(order, actor_id, "CASH")

    def record_manual(self, order: Order, actor_id: str, method: str, reference: str = "", amount: int | None = None,
                      commit: bool = True) -> Payment:
        """Money the laundry received directly: cash, or mobile money paid to its own till number."""
        if order.status in ("CANCELLED", "REJECTED"):
            raise AppError(409, "ORDER_CLOSED", "This order is no longer active")
        payment = self.latest(order.id)
        if payment and payment.status == "PROCESSING":
            raise AppError(409, "PAYMENT_IN_PROGRESS", "A mobile money payment is in progress for this order")
        owed = balance(order)
        if owed <= 0 or order.payment_status == "REFUNDED":
            raise AppError(409, "ALREADY_PAID", "This order has already been paid")
        amount = owed if amount is None else amount
        if amount > owed:
            raise AppError(422, "AMOUNT_TOO_LARGE", f"The balance is TZS {owed:,}", {"balance": owed})
        # Reuse the open placeholder created with the order; anything else (paid, refunded, a provider's) stays as history.
        if payment is None or payment.status not in ("PENDING", "FAILED") or payment.provider:
            payment = Payment(order_id=order.id, method=method, amount=amount, status="PENDING")
            self.db.add(payment)
            self.db.flush()
        payment.method, payment.amount = method, amount
        payment.recorded_by = actor_id
        if method == "MOBILE_MONEY":
            payment.provider = "manual"
            if reference:
                if self.db.scalar(select(Payment.id).where(Payment.provider_reference == reference)):
                    raise AppError(409, "DUPLICATE_REFERENCE", "This transaction reference was already recorded")
                payment.provider_reference = reference
        order.payment_method = method
        self._move(payment, order, "PAID", actor_id)
        if balance(order) > 0:
            # Keep one open placeholder for what is still owed.
            self.db.add(Payment(order_id=order.id, method=method, amount=balance(order), status="PENDING"))
        if commit:
            self.db.commit()
        return payment

    def refund(self, payment: Payment, actor_id: str, reason: str | None) -> Payment:
        order = self.db.get(Order, payment.order_id)
        self._move(payment, order, "REFUNDED", actor_id)
        from .commission import CommissionService  # local import: commission → models only, avoids a cycle

        CommissionService(self.db).reverse(order, reason or "Payment refunded")
        audit(self.db, actor_id, "PAYMENT_REFUND_REASON", "payment", payment.id, reason=reason)
        self.db.commit()
        return payment
