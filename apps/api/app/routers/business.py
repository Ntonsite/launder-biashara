import json
from fastapi import APIRouter,Depends,HTTPException,Query
from sqlalchemy import func,select
from sqlalchemy.orm import Session
from ..database import get_db
from ..dependencies import require_business
from ..models import AuditLog,Customer,Order,Service,User
from ..repositories.business import BusinessRepository
from ..schemas.business import BusinessOrderCreate,CustomerCreate,OnboardingUpdate,ServiceCreate
from ..services.business import BusinessRegistrationService
router=APIRouter(prefix="/business",tags=["Business"],dependencies=[Depends(require_business)])
def owned(db,user):
    business=BusinessRepository(db).for_owner(user.id)
    if not business:raise HTTPException(404,"Business not found")
    return business
@router.get("/profile")
def profile(db:Session=Depends(get_db),user:User=Depends(require_business)):
    b=owned(db,user);return {"id":b.id,"name":b.name,"slug":b.slug,"area":b.area,"status":b.status,"verification_status":b.verification_status}
@router.get("/onboarding")
def get_onboarding(db:Session=Depends(get_db),user:User=Depends(require_business)):
    b=owned(db,user);x=BusinessRepository(db).onboarding(b.id);return {"current_step":x.current_step,"data":json.loads(x.data_json),"completed":x.completed}
@router.put("/onboarding")
def save_onboarding(payload:OnboardingUpdate,db:Session=Depends(get_db),user:User=Depends(require_business)):
    b=owned(db,user);x=BusinessRepository(db).onboarding(b.id);x=BusinessRegistrationService(db).save_onboarding(b,x,payload.step,payload.data,payload.completed);return {"current_step":x.current_step,"completed":x.completed}
@router.get("/services")
def services(db:Session=Depends(get_db),user:User=Depends(require_business)):
    b=owned(db,user);return [{"id":x.id,"name":x.name,"description":x.description,"pricing_model":x.pricing_model,"price":x.price,"turnaround_hours":x.turnaround_hours,"active":x.active} for x in BusinessRepository(db).services(b.id)]
@router.post("/services",status_code=201)
def create_service(payload:ServiceCreate,db:Session=Depends(get_db),user:User=Depends(require_business)):
    b=owned(db,user);x=Service(business_id=b.id,**payload.model_dump());db.add(x);db.flush();db.add(AuditLog(actor_id=user.id,action="SERVICE_CREATED",entity="service",entity_id=x.id));db.commit();return {"id":x.id,**payload.model_dump()}
@router.put("/services/{service_id}")
def update_service(service_id:str,payload:ServiceCreate,db:Session=Depends(get_db),user:User=Depends(require_business)):
    b=owned(db,user);x=db.scalar(select(Service).where(Service.id==service_id,Service.business_id==b.id))
    if not x:raise HTTPException(404,"Service not found")
    for key,value in payload.model_dump().items():setattr(x,key,value)
    db.add(AuditLog(actor_id=user.id,action="SERVICE_UPDATED",entity="service",entity_id=x.id));db.commit();return {"id":x.id,**payload.model_dump()}
@router.delete("/services/{service_id}",status_code=204)
def delete_service(service_id:str,db:Session=Depends(get_db),user:User=Depends(require_business)):
    b=owned(db,user);x=db.scalar(select(Service).where(Service.id==service_id,Service.business_id==b.id))
    if not x:raise HTTPException(404,"Service not found")
    db.delete(x);db.commit()
@router.get("/customers")
def customers(q:str|None=None,db:Session=Depends(get_db),user:User=Depends(require_business)):
    b=owned(db,user);return [{"id":x.id,"name":x.name,"phone":x.phone,"email":x.email} for x in BusinessRepository(db).customers(b.id,q)]
@router.get("/orders")
def orders(q:str|None=None,status:str|None=None,page:int=Query(1,ge=1),page_size:int=Query(10,ge=5,le=100),db:Session=Depends(get_db),user:User=Depends(require_business)):
    b=owned(db,user);rows,total=BusinessRepository(db).orders(b.id,q,status,(page-1)*page_size,page_size);customers={x.id:x for x in db.scalars(select(Customer).where(Customer.id.in_([o.customer_id for o in rows])))};return {"items":[{"id":o.id,"order_number":o.order_number,"customer_name":customers[o.customer_id].name,"phone":customers[o.customer_id].phone,"source":o.source,"status":o.status,"payment_status":o.payment_status,"total":o.total,"created_at":o.created_at} for o in rows],"total":total,"page":page,"page_size":page_size}
@router.post("/orders",status_code=201)
def create_order(payload:BusinessOrderCreate,db:Session=Depends(get_db),user:User=Depends(require_business)):
    b=owned(db,user);customer=db.scalar(select(Customer).where(Customer.phone==payload.phone)) or Customer(name=payload.customer_name,phone=payload.phone);db.add(customer);db.flush();count=db.scalar(select(func.count(Order.id))) or 0;x=Order(order_number=f"LND-{26000+count}",business_id=b.id,customer_id=customer.id,source=payload.source,status="NEW",total=payload.total);db.add(x);db.flush();db.add(AuditLog(actor_id=user.id,action="ORDER_CREATED",entity="order",entity_id=x.id));db.commit();return {"id":x.id,"order_number":x.order_number,"status":x.status}
@router.get("/analytics")
def analytics(db:Session=Depends(get_db),user:User=Depends(require_business)):
    b=owned(db,user);count=db.scalar(select(func.count(Order.id)).where(Order.business_id==b.id)) or 0;revenue=db.scalar(select(func.coalesce(func.sum(Order.total),0)).where(Order.business_id==b.id)) or 0;return {"orders":count,"revenue":revenue,"average_order":int(revenue/count) if count else 0}
