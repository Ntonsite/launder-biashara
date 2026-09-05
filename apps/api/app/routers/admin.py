from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..dependencies import require_admin
from ..models import MarketplaceAccount,User
from ..repositories.admin import AdminRepository
from ..repositories.marketplace import MarketplaceRepository
from ..schemas.admin import MarketplaceDecision
from ..services.marketplace import MarketplaceAdminService
router=APIRouter(prefix="/admin",tags=["Administration"],dependencies=[Depends(require_admin)])
@router.get("/dashboard")
def dashboard(db:Session=Depends(get_db)):return AdminRepository(db).dashboard()
@router.get("/businesses")
def businesses(db:Session=Depends(get_db)):return [{"id":x.id,"name":x.name,"slug":x.slug,"area":x.area,"status":x.status,"verification_status":x.verification_status} for x in AdminRepository(db).businesses()]
@router.get("/marketplace-applications")
def applications(db:Session=Depends(get_db)):return [{"id":m.id,"business_id":b.id,"business_name":b.name,"area":b.area,"status":m.status,"commission_rate":m.commission_rate,"pickup_radius_km":m.pickup_radius_km} for m,b in MarketplaceRepository(db).applications()]
@router.post("/marketplace-applications/{application_id}/{decision}")
def decide(application_id:str,decision:str,payload:MarketplaceDecision,db:Session=Depends(get_db),actor:User=Depends(require_admin)):
    account=db.get(MarketplaceAccount,application_id)
    if not account:raise HTTPException(404,"Application not found")
    try:account=MarketplaceAdminService(db).decide(account,decision,actor,payload.reason)
    except ValueError as exc:raise HTTPException(400,str(exc))
    return {"id":account.id,"status":account.status}
@router.get("/orders")
def orders(db:Session=Depends(get_db)):return [{"id":x.id,"order_number":x.order_number,"status":x.status,"payment_status":x.payment_status,"total":x.total,"source":x.source} for x in AdminRepository(db).orders()]
@router.get("/customers")
def customers(db:Session=Depends(get_db)):return [{"id":x.id,"name":x.name,"phone":x.phone,"email":x.email} for x in AdminRepository(db).customers()]
@router.get("/reviews")
def reviews(db:Session=Depends(get_db)):return [{"id":x.id,"rating":x.rating,"comment":x.comment,"status":x.status} for x in AdminRepository(db).reviews()]
@router.get("/audit-logs")
def logs(db:Session=Depends(get_db)):return [{"action":x.action,"entity":x.entity,"entity_id":x.entity_id,"created_at":x.created_at} for x in AdminRepository(db).audit_logs()]
