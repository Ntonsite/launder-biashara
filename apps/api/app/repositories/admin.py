from sqlalchemy import func,select
from sqlalchemy.orm import Session
from ..models import AuditLog,Business,Customer,MarketplaceAccount,Order,Review
class AdminRepository:
    def __init__(self,db:Session):self.db=db
    def dashboard(self):
        gmv=self.db.scalar(select(func.coalesce(func.sum(Order.total),0))) or 0
        return {"businesses":self.db.scalar(select(func.count(Business.id))),"pending_applications":self.db.scalar(select(func.count(MarketplaceAccount.id)).where(MarketplaceAccount.status=="PENDING_REVIEW")),"customers":self.db.scalar(select(func.count(Customer.id))),"orders":self.db.scalar(select(func.count(Order.id))),"gmv":gmv,"platform_revenue":int(gmv*.05)}
    def businesses(self):return list(self.db.scalars(select(Business)))
    def orders(self):return list(self.db.scalars(select(Order).order_by(Order.created_at.desc())))
    def customers(self):return list(self.db.scalars(select(Customer)))
    def reviews(self):return list(self.db.scalars(select(Review)))
    def audit_logs(self):return list(self.db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc())))
