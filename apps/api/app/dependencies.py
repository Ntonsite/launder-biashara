from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from .core.security import decode_token
from .database import get_db
from .models import User
bearer=HTTPBearer(auto_error=False)
def current_user(credentials:HTTPAuthorizationCredentials=Depends(bearer),db:Session=Depends(get_db))->User:
    if not credentials:raise HTTPException(401,"Authentication required")
    try:user_id=decode_token(credentials.credentials)["sub"]
    except (ValueError,KeyError):raise HTTPException(401,"Invalid or expired token")
    user=db.get(User,user_id)
    if not user or not user.active:raise HTTPException(401,"Inactive user")
    return user
def require_admin(user:User=Depends(current_user))->User:
    if user.role not in ("ADMIN","SUPER_ADMIN"):raise HTTPException(403,"Admin permission required")
    return user
def require_business(user:User=Depends(current_user))->User:
    if user.role not in ("BUSINESS_OWNER","BRANCH_MANAGER"):raise HTTPException(403,"Business permission required")
    return user
