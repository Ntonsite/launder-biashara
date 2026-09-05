from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from passlib.context import CryptContext
from .config import settings

passwords=CryptContext(schemes=["bcrypt"],deprecated="auto")
def hash_password(value:str)->str:return passwords.hash(value)
def verify_password(value:str,hashed:str)->bool:return passwords.verify(value,hashed)
def create_access_token(user_id:str,role:str)->str:return jwt.encode({"sub":user_id,"role":role,"exp":datetime.now(timezone.utc)+timedelta(hours=settings.access_token_hours)},settings.jwt_secret,algorithm=settings.jwt_algorithm)
def decode_token(token:str)->dict:
    try:return jwt.decode(token,settings.jwt_secret,algorithms=[settings.jwt_algorithm])
    except JWTError as exc:raise ValueError("Invalid or expired token") from exc
