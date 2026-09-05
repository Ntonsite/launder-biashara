from sqlalchemy import select
from sqlalchemy.orm import Session
from ..models import Business, MarketplaceAccount
class MarketplaceRepository:
    def __init__(self,db:Session):self.db=db
    def active_businesses(self,q:str|None=None):
        stmt=select(Business).join(MarketplaceAccount).where(MarketplaceAccount.status=="ACTIVE")
        if q:stmt=stmt.where(Business.name.ilike(f"%{q}%")|Business.area.ilike(f"%{q}%"))
        return list(self.db.scalars(stmt))
    def account_for_owner(self,owner_id:str):
        business=self.db.scalar(select(Business).where(Business.owner_id==owner_id));return (business,self.db.scalar(select(MarketplaceAccount).where(MarketplaceAccount.business_id==business.id))) if business else (None,None)
    def applications(self):return list(self.db.execute(select(MarketplaceAccount,Business).join(Business)).all())
