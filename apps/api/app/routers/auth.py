from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import current_user
from ..models import Customer, User
from ..schemas.auth import BusinessRegisterRequest, LoginRequest, OtpRequest, OtpVerify, ProfileUpdate, RefreshRequest, TokenResponse
from ..services.audit import audit
from ..services.auth import AuthenticationService, OtpService, TokenService, user_payload
from ..services.business import BusinessRegistrationService

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    """Business staff and administrators."""
    return AuthenticationService(db).authenticate(payload.email, payload.password)


@router.post("/business/register", response_model=TokenResponse, status_code=201)
def register(payload: BusinessRegisterRequest, db: Session = Depends(get_db)):
    user, _ = BusinessRegistrationService(db).register(payload)
    return TokenService(db).issue(user)


@router.post("/otp/request")
def otp_request(payload: OtpRequest, db: Session = Depends(get_db)):
    """Marketplace customers: send a one-time code to a Tanzanian mobile number."""
    return OtpService(db).request(payload.phone)


@router.post("/otp/verify")
def otp_verify(payload: OtpVerify, db: Session = Depends(get_db)):
    return OtpService(db).verify(payload.phone, payload.code)


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)):
    return TokenService(db).refresh(payload.refresh_token)


@router.post("/logout", status_code=204)
def logout(payload: RefreshRequest, db: Session = Depends(get_db)):
    TokenService(db).revoke(payload.refresh_token)


@router.get("/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return user_payload(db, user)


@router.patch("/me")
def update_me(payload: ProfileUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if payload.full_name is not None:
        user.full_name = payload.full_name.strip()
        if user.role == "CUSTOMER":
            record = db.query(Customer).filter(Customer.user_id == user.id).first()
            if record and not record.name:
                record.name = user.full_name
    if payload.language is not None:
        user.language = payload.language
    audit(db, user.id, "PROFILE_UPDATED", "user", user.id)
    db.commit()
    return user_payload(db, user)
