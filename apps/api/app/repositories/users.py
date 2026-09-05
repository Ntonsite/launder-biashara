from sqlalchemy import select
from sqlalchemy.orm import Session
from ..models import User
class UserRepository:
    def __init__(self,db:Session):self.db=db
    def by_email(self,email:str):return self.db.scalar(select(User).where(User.email==email.lower()))
    def by_id(self,user_id:str):return self.db.get(User,user_id)
