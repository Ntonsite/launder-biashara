"""In-app notifications for customers. Rows are the source of truth for the app's inbox.

Push delivery is not configured in Phase 1 (no FCM/APNs credentials). Rows are created with
push_status=NOT_CONFIGURED so nothing ever claims a push was sent.
"""
import json

from sqlalchemy.orm import Session

from ..models import Customer, Notification, Order

STATUS_NOTIFICATIONS = {
    "ACCEPTED": "ORDER_ACCEPTED",
    "AWAITING_PICKUP": "PICKUP_SCHEDULED",
    "WASHING": "ORDER_WASHING",
    "READY": "ORDER_READY",
    "OUT_FOR_DELIVERY": "ORDER_OUT_FOR_DELIVERY",
    "DELIVERED": "ORDER_DELIVERED",
    "REJECTED": "ORDER_REJECTED",
    "CANCELLED": "ORDER_CANCELLED",
}


def notify_order(db: Session, order: Order, kind: str) -> None:
    customer = db.get(Customer, order.customer_id)
    if not customer or not customer.user_id:
        return  # walk-in customers without an app account
    db.add(Notification(user_id=customer.user_id, kind=kind, order_id=order.id,
                        data_json=json.dumps({"order_number": order.order_number, "status": order.status})))


def notify_status(db: Session, order: Order, status: str) -> None:
    kind = STATUS_NOTIFICATIONS.get(status)
    if kind:
        notify_order(db, order, kind)
