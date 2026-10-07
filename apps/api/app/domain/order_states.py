"""Order lifecycle rules. The only place that decides whether a status change is legal.

Processing stages may be skipped forward (e.g. an iron-only order goes RECEIVED → IRONING), but never backwards,
and fulfilment decides whether the pickup/delivery legs exist at all.
"""
NEW = "NEW"
ACCEPTED = "ACCEPTED"
AWAITING_PICKUP = "AWAITING_PICKUP"
RECEIVED = "RECEIVED"
WASHING = "WASHING"
DRYING = "DRYING"
IRONING = "IRONING"
QUALITY_CHECK = "QUALITY_CHECK"
READY = "READY"
OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"
DELIVERED = "DELIVERED"
COMPLETED = "COMPLETED"
CANCELLED = "CANCELLED"
REJECTED = "REJECTED"

FLOW = [NEW, ACCEPTED, AWAITING_PICKUP, RECEIVED, WASHING, DRYING, IRONING, QUALITY_CHECK, READY, OUT_FOR_DELIVERY,
        DELIVERED, COMPLETED]
ALL_STATUSES = FLOW + [CANCELLED, REJECTED]
TERMINAL = {COMPLETED, CANCELLED, REJECTED}
ACTIVE = set(FLOW) - {COMPLETED}

_TRANSITIONS: dict[str, set[str]] = {
    NEW: {ACCEPTED, REJECTED, CANCELLED},
    ACCEPTED: {AWAITING_PICKUP, RECEIVED, CANCELLED},
    AWAITING_PICKUP: {RECEIVED, CANCELLED},
    RECEIVED: {WASHING, DRYING, IRONING, QUALITY_CHECK, READY, CANCELLED},
    WASHING: {DRYING, IRONING, QUALITY_CHECK, READY},
    DRYING: {IRONING, QUALITY_CHECK, READY},
    IRONING: {QUALITY_CHECK, READY},
    QUALITY_CHECK: {READY},
    READY: {OUT_FOR_DELIVERY, DELIVERED},
    OUT_FOR_DELIVERY: {DELIVERED},
    DELIVERED: {COMPLETED},
}

PICKUP_ONLY = {AWAITING_PICKUP, OUT_FOR_DELIVERY}


def allowed_next(status: str, fulfillment: str) -> list[str]:
    options = _TRANSITIONS.get(status, set())
    if fulfillment != "PICKUP":
        options = options - PICKUP_ONLY
    # A pickup order must physically come back to the customer via OUT_FOR_DELIVERY.
    if fulfillment == "PICKUP" and status == READY:
        options = options - {DELIVERED}
    # Keep the canonical display order.
    return [s for s in ALL_STATUSES if s in options]


def can_transition(current: str, target: str, fulfillment: str) -> bool:
    return target in allowed_next(current, fulfillment)


def customer_can_cancel(status: str) -> bool:
    return status == NEW


def stage_for_customer(status: str, fulfillment: str) -> list[str]:
    """The timeline a customer sees for this order (optional stages remain visible as the standard path)."""
    stages = [NEW, ACCEPTED]
    if fulfillment == "PICKUP":
        stages.append(AWAITING_PICKUP)
    stages += [RECEIVED, WASHING, DRYING, IRONING, QUALITY_CHECK, READY]
    if fulfillment == "PICKUP":
        stages.append(OUT_FOR_DELIVERY)
    stages += [DELIVERED, COMPLETED]
    return stages
