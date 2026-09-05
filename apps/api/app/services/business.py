import json,re
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..core.security import hash_password
from ..models import AuditLog,Business,BusinessOnboarding,MarketplaceAccount,User
from ..schemas.auth import BusinessRegisterRequest
class BusinessRegistrationService:
    def __init__(self,db:Session):self.db=db
    def register(self,payload:BusinessRegisterRequest):
        if self.db.scalar(select(User).where(User.email==payload.email.lower())):raise ValueError("An account with this email already exists")
        base=re.sub(r"[^a-z0-9]+","-",payload.business_name.lower()).strip("-") or "laundry";slug=base;number=2
        while self.db.scalar(select(Business).where(Business.slug==slug)):slug=f"{base}-{number}";number+=1
        user=User(email=payload.email.lower(),password_hash=hash_password(payload.password),full_name=payload.full_name,role="BUSINESS_OWNER");self.db.add(user);self.db.flush()
        business=Business(owner_id=user.id,name=payload.business_name,slug=slug,area="Not set",status="ONBOARDING",verification_status="UNVERIFIED",latitude=-6.7924,longitude=39.2083,pickup_enabled=False);self.db.add(business);self.db.flush();self.db.add_all([BusinessOnboarding(business_id=business.id),MarketplaceAccount(business_id=business.id,status="NOT_ENROLLED"),AuditLog(actor_id=user.id,action="BUSINESS_REGISTERED",entity="business",entity_id=business.id)]);self.db.commit();return user,business
    def save_onboarding(self,business:Business,record:BusinessOnboarding,step:int,data:dict,completed:bool):
        stored=json.loads(record.data_json or "{}");stored[str(step)]=data;record.data_json=json.dumps(stored);record.current_step=max(record.current_step,min(step+1,9));record.completed=completed
        if completed:business.status="ACTIVE"
        self.db.add(AuditLog(actor_id=business.owner_id,action="ONBOARDING_UPDATED",entity="business",entity_id=business.id));self.db.commit();return record
