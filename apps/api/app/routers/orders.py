from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy import func,select
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Business,Customer,Order
from ..schemas.orders import OrderCreate
router=APIRouter(prefix="/orders",tags=["Orders"])
@router.post("",status_code=201)
def create_order(payload:OrderCreate,db:Session=Depends(get_db)):
    business=db.scalar(select(Business).where(Business.slug==payload.laundry_slug))
    if not business:raise HTTPException(404,"Laundry not found")
    customer=db.scalar(select(Customer).where(Customer.phone==payload.phone)) or Customer(name=payload.customer_name,phone=payload.phone);db.add(customer);db.flush();number=f"LND-{24091+db.scalar(select(func.count(Order.id)))}";order=Order(order_number=number,business_id=business.id,customer_id=customer.id,source="MARKETPLACE",status="NEW",total=payload.total);db.add(order);db.commit();return {"id":order.id,"order_number":order.order_number,"status":order.status}
