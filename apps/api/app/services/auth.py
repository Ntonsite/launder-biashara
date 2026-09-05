from sqlalchemy.orm import Session
from ..core.security import create_access_token,verify_password
from ..models import AuditLog
from ..repositories.users import UserRepository
class AuthenticationService:
    def __init__(self,db:Session):self.db=db;self.users=UserRepository(db)
    def authenticate(self,email:str,password:str):
        user=self.users.by_email(email)
        if not user or not verify_password(password,user.password_hash):return None
        self.db.add(AuditLog(actor_id=user.id,action="LOGIN",entity="user",entity_id=user.id));self.db.commit()
        return {"access_token":create_access_token(user.id,user.role),"user":{"id":user.id,"name":user.full_name,"email":user.email,"role":user.role,"language":user.language}}
