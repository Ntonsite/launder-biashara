from datetime import datetime,timezone
from sqlalchemy import func,select
from .core.security import hash_password
from .database import Base,SessionLocal,engine
from .models import Branch,Business,Customer,MarketplaceAccount,Order,Service,User
def seed_database():
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if db.scalar(select(func.count(User.id))):
            business=db.scalar(select(Business).where(Business.slug=="t-laundry-mikocheni"));customers=list(db.scalars(select(Customer)))
            if business and not db.scalar(select(func.count(Service.id)).where(Service.business_id==business.id)):
                db.add_all([Service(business_id=business.id,name=name,pricing_model=model,price=price,turnaround_hours=hours) for name,model,price,hours in [("Shirt","PER_ITEM",2000,24),("Trouser","PER_ITEM",3000,24),("Suit","PER_ITEM",8000,48),("Wash & Fold","PER_KG",4000,24)]])
            if business and not db.scalar(select(func.count(Branch.id)).where(Branch.business_id==business.id)):db.add(Branch(business_id=business.id,name="Mikocheni Branch",address="Mikocheni B, Dar es Salaam",phone="+255 712 345 678",latitude=-6.7734,longitude=39.2301))
            existing=db.scalar(select(func.count(Order.id))) or 0
            if business and customers and existing<45:
                sources=["WALK_IN","MARKETPLACE","PHONE","WHATSAPP"];statuses=["NEW","ACCEPTED","WASHING","DRYING","IRONING","READY","DELIVERED"]
                for i in range(existing,46):db.add(Order(order_number=f"LND-{25000+i}",business_id=business.id,customer_id=customers[i%len(customers)].id,source=sources[i%len(sources)],status=statuses[i%len(statuses)],payment_status="PAID" if statuses[i%len(statuses)]=="DELIVERED" else "PENDING",total=10500+(i%9)*2750))
            db.commit()
            return
        owner=User(email="owner@t-laundry.co.tz",password_hash=hash_password("Demo123!"),full_name="Asha Mushi",role="BUSINESS_OWNER");admin=User(email="admin@launder.co.tz",password_hash=hash_password("Admin123!"),full_name="Launder Admin",role="SUPER_ADMIN");db.add_all([owner,admin]);db.flush()
        business=Business(owner_id=owner.id,name="T-Laundry",slug="t-laundry-mikocheni",area="Mikocheni",latitude=-6.7734,longitude=39.2301,rating=4.9,pickup_enabled=True);db.add(business);db.flush();db.add_all([MarketplaceAccount(business_id=business.id,status="PENDING_REVIEW",commission_rate=5,pickup_radius_km=8,submitted_at=datetime.now(timezone.utc)),Branch(business_id=business.id,name="Mikocheni Branch",address="Mikocheni B, Dar es Salaam",phone="+255 712 345 678",latitude=-6.7734,longitude=39.2301)]);db.add_all([Service(business_id=business.id,name=name,pricing_model=model,price=price,turnaround_hours=hours) for name,model,price,hours in [("Shirt","PER_ITEM",2000,24),("Trouser","PER_ITEM",3000,24),("Suit","PER_ITEM",8000,48),("Wash & Fold","PER_KG",4000,24)]])
        customers=[Customer(name="Neema Juma",phone="0712334901",email="neema@example.com"),Customer(name="Baraka Said",phone="0754102820"),Customer(name="Zawadi Omar",phone="0687551004")];db.add_all(customers);db.flush()
        for i,(customer,source,state,total) in enumerate(zip(customers,["MARKETPLACE","WALK_IN","PHONE"],["WASHING","READY","DELIVERED"],[18500,32000,12500])):db.add(Order(order_number=f"LND-{24091-i}",business_id=business.id,customer_id=customer.id,source=source,status=state,payment_status="PAID" if state=="DELIVERED" else "PENDING",total=total))
        db.commit()
