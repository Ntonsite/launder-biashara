from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..dependencies import current_user
from ..models import User
from ..schemas.auth import BusinessRegisterRequest,LoginRequest,TokenResponse
from ..services.business import BusinessRegistrationService
from ..core.security import create_access_token
from ..services.auth import AuthenticationService
router=APIRouter(prefix="/auth",tags=["Authentication"])
@router.post("/login",response_model=TokenResponse)
def login(payload:LoginRequest,db:Session=Depends(get_db)):
    result=AuthenticationService(db).authenticate(payload.email,payload.password)
    if not result:raise HTTPException(401,"Incorrect email or password")
    return result
@router.post("/business/register",response_model=TokenResponse,status_code=201)
def register(payload:BusinessRegisterRequest,db:Session=Depends(get_db)):
    try:user,business=BusinessRegistrationService(db).register(payload)
    except ValueError as exc:raise HTTPException(409,str(exc))
    return {"access_token":create_access_token(user.id,user.role),"user":{"id":user.id,"name":user.full_name,"email":user.email,"role":user.role,"business_id":business.id,"language":user.language}}
@router.get("/me")
def me(user:User=Depends(current_user)):return {"id":user.id,"name":user.full_name,"email":user.email,"role":user.role,"language":user.language}
