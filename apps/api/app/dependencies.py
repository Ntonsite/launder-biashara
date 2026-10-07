from dataclasses import dataclass

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .core.errors import AppError
from .core.security import decode_token
from .database import get_db
from .models import Business, User

bearer = HTTPBearer(auto_error=False)

ADMIN_ROLES = ("ADMIN", "SUPER_ADMIN")
BUSINESS_ROLES = ("BUSINESS_OWNER", "BRANCH_MANAGER", "STAFF")


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
    if not credentials:
        raise AppError(401, "UNAUTHENTICATED", "Authentication required")
    try:
        user_id = decode_token(credentials.credentials)["sub"]
    except (ValueError, KeyError):
        raise AppError(401, "TOKEN_EXPIRED", "Your session has expired. Please sign in again.") from None
    user = db.get(User, user_id)
    if not user or not user.active:
        raise AppError(401, "UNAUTHENTICATED", "Account is not active")
    return user


def optional_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User | None:
    if not credentials:
        return None
    try:
        return current_user(credentials, db)
    except AppError:
        return None


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role not in ADMIN_ROLES:
        raise AppError(403, "FORBIDDEN", "Admin permission required")
    return user


def require_customer(user: User = Depends(current_user)) -> User:
    if user.role != "CUSTOMER":
        raise AppError(403, "FORBIDDEN", "Customer account required")
    return user


def require_business(user: User = Depends(current_user)) -> User:
    if user.role not in BUSINESS_ROLES:
        raise AppError(403, "FORBIDDEN", "Business permission required")
    return user


@dataclass
class BusinessContext:
    user: User
    business: Business

    @property
    def is_owner(self) -> bool:
        return self.user.role == "BUSINESS_OWNER"

    def require_owner(self) -> None:
        if not self.is_owner:
            raise AppError(403, "FORBIDDEN", "Only the business owner can do this")

    def require_manager(self) -> None:
        if self.user.role not in ("BUSINESS_OWNER", "BRANCH_MANAGER"):
            raise AppError(403, "FORBIDDEN", "Manager permission required")


def business_context(user: User = Depends(require_business), db: Session = Depends(get_db)) -> BusinessContext:
    if user.role == "BUSINESS_OWNER":
        business = db.scalar(select(Business).where(Business.owner_id == user.id))
    else:
        business = db.get(Business, user.business_id) if user.business_id else None
    if not business:
        raise AppError(404, "NOT_FOUND", "Business not found")
    return BusinessContext(user=user, business=business)
