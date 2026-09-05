from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from ..database import Base

def uuid(): return str(uuid4())
def utcnow(): return datetime.now(timezone.utc)
class User(Base):
    __tablename__="users"; id:Mapped[str]=mapped_column(String,primary_key=True,default=uuid); email:Mapped[str]=mapped_column(String,unique=True,index=True); password_hash:Mapped[str]=mapped_column(String); full_name:Mapped[str]=mapped_column(String); role:Mapped[str]=mapped_column(String,index=True); active:Mapped[bool]=mapped_column(Boolean,default=True); language:Mapped[str]=mapped_column(String,default="en")
class Business(Base):
    __tablename__="businesses"; id:Mapped[str]=mapped_column(String,primary_key=True,default=uuid); owner_id:Mapped[str]=mapped_column(ForeignKey("users.id")); name:Mapped[str]=mapped_column(String); slug:Mapped[str]=mapped_column(String,unique=True,index=True); area:Mapped[str]=mapped_column(String); status:Mapped[str]=mapped_column(String,default="ACTIVE"); verification_status:Mapped[str]=mapped_column(String,default="VERIFIED"); latitude:Mapped[float]=mapped_column(Float); longitude:Mapped[float]=mapped_column(Float); rating:Mapped[float]=mapped_column(Float,default=0); pickup_enabled:Mapped[bool]=mapped_column(Boolean,default=False); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
class Branch(Base):
    __tablename__="branches"; id:Mapped[str]=mapped_column(String,primary_key=True,default=uuid); business_id:Mapped[str]=mapped_column(ForeignKey("businesses.id"),index=True); name:Mapped[str]=mapped_column(String); address:Mapped[str]=mapped_column(String); city:Mapped[str]=mapped_column(String,default="Dar es Salaam"); region:Mapped[str]=mapped_column(String,default="Dar es Salaam"); phone:Mapped[str]=mapped_column(String); latitude:Mapped[float]=mapped_column(Float); longitude:Mapped[float]=mapped_column(Float); active:Mapped[bool]=mapped_column(Boolean,default=True)
class BusinessOnboarding(Base):
    __tablename__="business_onboarding"; id:Mapped[str]=mapped_column(String,primary_key=True,default=uuid); business_id:Mapped[str]=mapped_column(ForeignKey("businesses.id"),unique=True,index=True); current_step:Mapped[int]=mapped_column(Integer,default=1); data_json:Mapped[str]=mapped_column(String,default="{}"); completed:Mapped[bool]=mapped_column(Boolean,default=False); updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow,onupdate=utcnow)
class Service(Base):
    __tablename__="services"; id:Mapped[str]=mapped_column(String,primary_key=True,default=uuid); business_id:Mapped[str]=mapped_column(ForeignKey("businesses.id"),index=True); name:Mapped[str]=mapped_column(String); description:Mapped[str]=mapped_column(String,default=""); pricing_model:Mapped[str]=mapped_column(String,default="PER_ITEM"); price:Mapped[int]=mapped_column(Integer); turnaround_hours:Mapped[int]=mapped_column(Integer,default=24); active:Mapped[bool]=mapped_column(Boolean,default=True)
class MarketplaceAccount(Base):
    __tablename__="marketplace_accounts"; id:Mapped[str]=mapped_column(String,primary_key=True,default=uuid); business_id:Mapped[str]=mapped_column(ForeignKey("businesses.id"),unique=True,index=True); status:Mapped[str]=mapped_column(String,index=True,default="NOT_ENROLLED"); commission_rate:Mapped[float]=mapped_column(Float,default=5); pickup_radius_km:Mapped[float]=mapped_column(Float,default=8); submitted_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True)); approved_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True)); rejection_reason:Mapped[str|None]=mapped_column(String)
class Customer(Base):
    __tablename__="customers"; id:Mapped[str]=mapped_column(String,primary_key=True,default=uuid); name:Mapped[str]=mapped_column(String,index=True); phone:Mapped[str]=mapped_column(String,unique=True,index=True); email:Mapped[str|None]=mapped_column(String)
class Order(Base):
    __tablename__="orders"; id:Mapped[str]=mapped_column(String,primary_key=True,default=uuid); order_number:Mapped[str]=mapped_column(String,unique=True,index=True); business_id:Mapped[str]=mapped_column(ForeignKey("businesses.id"),index=True); customer_id:Mapped[str]=mapped_column(ForeignKey("customers.id")); source:Mapped[str]=mapped_column(String); status:Mapped[str]=mapped_column(String,index=True); payment_status:Mapped[str]=mapped_column(String,index=True,default="PENDING"); total:Mapped[int]=mapped_column(Integer); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
class Review(Base):
    __tablename__="reviews"; id:Mapped[str]=mapped_column(String,primary_key=True,default=uuid); order_id:Mapped[str]=mapped_column(ForeignKey("orders.id"),unique=True); rating:Mapped[int]=mapped_column(Integer); comment:Mapped[str]=mapped_column(String); status:Mapped[str]=mapped_column(String,default="PUBLISHED")
class AuditLog(Base):
    __tablename__="audit_logs"; id:Mapped[str]=mapped_column(String,primary_key=True,default=uuid); actor_id:Mapped[str]=mapped_column(String,index=True); action:Mapped[str]=mapped_column(String,index=True); entity:Mapped[str]=mapped_column(String); entity_id:Mapped[str]=mapped_column(String); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
