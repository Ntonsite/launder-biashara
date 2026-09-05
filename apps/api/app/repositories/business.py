import json
from sqlalchemy import func,select
from sqlalchemy.orm import Session
from ..models import Branch,Business,BusinessOnboarding,Customer,MarketplaceAccount,Order,Service
class BusinessRepository:
    def __init__(self,db:Session):self.db=db
    def for_owner(self,owner_id:str):return self.db.scalar(select(Business).where(Business.owner_id==owner_id))
    def onboarding(self,business_id:str):return self.db.scalar(select(BusinessOnboarding).where(BusinessOnboarding.business_id==business_id))
    def services(self,business_id:str):return list(self.db.scalars(select(Service).where(Service.business_id==business_id).order_by(Service.name)))
    def customers(self,business_id:str,q:str|None=None):
        stmt=select(Customer).join(Order,Order.customer_id==Customer.id).where(Order.business_id==business_id).distinct()
        if q:stmt=stmt.where(Customer.name.ilike(f"%{q}%")|Customer.phone.ilike(f"%{q}%"))
        return list(self.db.scalars(stmt))
    def orders(self,business_id:str,q:str|None=None,status:str|None=None,offset:int=0,limit:int=10):
        base=select(Order).where(Order.business_id==business_id)
        if status:base=base.where(Order.status==status)
        if q:base=base.join(Customer).where(Order.order_number.ilike(f"%{q}%")|Customer.name.ilike(f"%{q}%")|Customer.phone.ilike(f"%{q}%"))
        total=self.db.scalar(select(func.count()).select_from(base.subquery())) or 0
        return list(self.db.scalars(base.order_by(Order.created_at.desc()).offset(offset).limit(limit))),total
