import json

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.errors import AppError
from ..database import get_db
from ..schemas.orders import SandboxPaymentOutcome
from ..services.payments import PaymentService, payment_out, verify_signature

router = APIRouter(tags=["Payments"])


@router.post("/payments/webhooks/sandbox")
async def sandbox_webhook(request: Request, signature: str | None = Header(None, alias="X-Launder-Signature"),
                          db: Session = Depends(get_db)):
    """Provider callback. The body is HMAC-SHA256 signed with PAYMENT_WEBHOOK_SECRET; unsigned calls are refused."""
    body = await request.body()
    if not verify_signature(body, signature):
        raise AppError(401, "INVALID_SIGNATURE", "Invalid webhook signature")
    data = json.loads(body)
    outcome = data.get("status")
    if outcome not in ("PAID", "FAILED") or not data.get("reference"):
        raise AppError(422, "VALIDATION_ERROR", "reference and status (PAID|FAILED) are required")
    return payment_out(PaymentService(db).apply_provider_result(data["reference"], outcome, data.get("reason")))


@router.post("/dev/payments/{reference}/simulate", include_in_schema=settings.dev_tools_enabled)
def simulate(reference: str, payload: SandboxPaymentOutcome, db: Session = Depends(get_db)):
    """Development only: stands in for the customer approving or declining the prompt on their phone."""
    if not settings.dev_tools_enabled:
        raise AppError(404, "NOT_FOUND", "Not found")
    return payment_out(PaymentService(db).apply_provider_result(reference, payload.outcome, payload.reason))
