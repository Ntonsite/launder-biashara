from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..dependencies import require_business
from ..models import User
from ..repositories.marketplace import MarketplaceRepository
router=APIRouter(tags=["Marketplace"])
@router.get("/marketplace/laundries")
def laundries(q:str|None=None,db:Session=Depends(get_db)):
    rows=MarketplaceRepository(db).active_businesses(q);return {"items":[{"id":x.id,"slug":x.slug,"name":x.name,"area":x.area,"rating":x.rating,"pickup_enabled":x.pickup_enabled} for x in rows],"total":len(rows),"page":1,"page_size":20}
@router.get("/business/marketplace")
def business_marketplace(db:Session=Depends(get_db),user:User=Depends(require_business)):
    business,account=MarketplaceRepository(db).account_for_owner(user.id)
    if not business:raise HTTPException(404,"Business not found")
    return {"business_name":business.name,"slug":business.slug,"status":account.status if account else "NOT_ENROLLED","commission_rate":account.commission_rate if account else None,"pickup_radius_km":account.pickup_radius_km if account else None}
