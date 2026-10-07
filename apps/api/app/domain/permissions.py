"""What each business role may see and do. The single source for backend checks and for the web navigation.

OWNER     runs the business: money, performance, customers, marketplace, every report.
MANAGER   runs the day: operations, orders, payments, team, daily/weekly/orders/payments reports.
CASHIER   reception: create orders, find customers, take payments, hand over ready orders.
STAFF     laundry floor: the work queue, items, processing stages, due times. No money figures.
DRIVER    pickups and deliveries for pickup orders, and cash collected on delivery.
"""
from . import order_states as S

OWNER, MANAGER, CASHIER, STAFF, DRIVER = "BUSINESS_OWNER", "BRANCH_MANAGER", "CASHIER", "STAFF", "DRIVER"
BUSINESS_ROLES = (OWNER, MANAGER, CASHIER, STAFF, DRIVER)
ASSIGNABLE_ROLES = (MANAGER, CASHIER, STAFF, DRIVER)

_OPERATIONS = {"orders.view", "dashboard.operations"}
_FRONT_DESK = _OPERATIONS | {"orders.create", "payments.record", "customers.view", "money.view"}
_MANAGER = _FRONT_DESK | {"orders.edit", "services.manage", "settings.manage", "staff.view", "marketplace.view",
                          "reports.operational"}
CAPABILITIES: dict[str, frozenset[str]] = {
    OWNER: frozenset(_MANAGER | {"staff.manage", "marketplace.manage", "reports.business", "performance.view"}),
    MANAGER: frozenset(_MANAGER),
    CASHIER: frozenset(_FRONT_DESK | {"orders.edit"}),
    STAFF: frozenset(_OPERATIONS),
    DRIVER: frozenset(_OPERATIONS | {"payments.record", "orders.deliveries_only"}),
}

# Status changes a role may make. None = every transition the order state machine allows.
_TARGETS: dict[str, set[str] | None] = {
    OWNER: None,
    MANAGER: None,
    STAFF: None,
    CASHIER: {S.ACCEPTED, S.RECEIVED, S.DELIVERED, S.COMPLETED},
    DRIVER: {S.RECEIVED, S.OUT_FOR_DELIVERY, S.DELIVERED},
}

# Statuses a driver works on (pickup orders only).
DRIVER_STATUSES = (S.ACCEPTED, S.AWAITING_PICKUP, S.READY, S.OUT_FOR_DELIVERY)

REPORT_CAPABILITY = {
    "daily": "reports.operational", "weekly": "reports.operational", "orders": "reports.operational",
    "payments": "reports.operational", "monthly": "reports.business", "sales": "reports.business",
    "customers": "reports.business", "marketplace": "reports.business",
}


def capabilities(role: str) -> frozenset[str]:
    return CAPABILITIES.get(role, frozenset())


def can(role: str, capability: str) -> bool:
    return capability in capabilities(role)


def may_move_to(role: str, target: str, current: str, fulfillment: str) -> bool:
    allowed = _TARGETS.get(role, set())
    if role == DRIVER:
        if fulfillment != "PICKUP":
            return False
        # A driver only receives clothes they collected, not walk-in drop-offs.
        if target == S.RECEIVED and current != S.AWAITING_PICKUP:
            return False
    return allowed is None or target in allowed
