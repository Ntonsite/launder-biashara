from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..models import BusinessOnboarding, Customer, Order, Service


class BusinessRepository:
    def __init__(self, db: Session):
        self.db = db

    def onboarding(self, business_id: str) -> BusinessOnboarding:
        record = self.db.scalar(select(BusinessOnboarding).where(BusinessOnboarding.business_id == business_id))
        if record is None:
            record = BusinessOnboarding(business_id=business_id)
            self.db.add(record)
            self.db.flush()
        return record

    def services(self, business_id: str):
        return list(self.db.scalars(select(Service).where(Service.business_id == business_id)
                                    .order_by(Service.category, Service.sort_order, Service.name)))

    def customers_stmt(self, business_id: str, q: str | None = None):
        stmt = select(Customer).where(Customer.id.in_(select(Order.customer_id).where(Order.business_id == business_id)))
        if q:
            stmt = stmt.where(or_(Customer.name.ilike(f"%{q}%"), Customer.phone.ilike(f"%{q}%")))
        return stmt.order_by(Customer.name)

    def orders_stmt(self, business_id: str, q: str | None = None, status: str | None = None, source: str | None = None):
        stmt = select(Order).where(Order.business_id == business_id)
        if status:
            stmt = stmt.where(Order.status.in_(status.split(",")))
        if source:
            stmt = stmt.where(Order.source == source)
        if q:
            stmt = stmt.join(Customer, Customer.id == Order.customer_id).where(
                or_(Order.order_number.ilike(f"%{q}%"), Customer.name.ilike(f"%{q}%"), Customer.phone.ilike(f"%{q}%")))
        return stmt.order_by(Order.created_at.desc())
