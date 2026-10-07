import logging
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..core import ratelimit
from ..core.config import settings
from ..core.errors import AppError
from ..core.security import constant_time_equals, create_access_token, hash_secret, new_opaque_token, new_otp_code, verify_password
from ..domain.clock import as_utc, now_utc
from ..domain.phone import mask_phone, normalize_tz_phone
from ..models import Business, Customer, OtpChallenge, RefreshToken, User
from .audit import audit

log = logging.getLogger("launder.auth")


def user_payload(db: Session, user: User) -> dict:
    business_id = user.business_id
    if user.role == "BUSINESS_OWNER":
        business_id = db.scalar(select(Business.id).where(Business.owner_id == user.id))
    return {"id": user.id, "name": user.full_name, "email": user.email, "phone": user.phone, "role": user.role,
            "business_id": business_id, "language": user.language}


class TokenService:
    def __init__(self, db: Session):
        self.db = db

    def issue(self, user: User, family_id: str | None = None) -> dict:
        raw = new_opaque_token()
        self.db.add(RefreshToken(user_id=user.id, token_hash=hash_secret(raw), family_id=family_id or str(uuid4()),
                                 expires_at=now_utc() + timedelta(days=settings.refresh_token_days)))
        self.db.commit()
        return {"access_token": create_access_token(user.id, user.role), "refresh_token": raw, "token_type": "bearer",
                "expires_in": settings.access_token_minutes * 60, "user": user_payload(self.db, user)}

    def refresh(self, raw: str) -> dict:
        token = self.db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_secret(raw)))
        if not token:
            raise AppError(401, "SESSION_EXPIRED", "Your session has expired. Please sign in again.")
        if token.revoked_at is not None:
            # A rotated token was replayed: assume theft and end every session from that login.
            self.db.execute(update(RefreshToken).where(RefreshToken.family_id == token.family_id, RefreshToken.revoked_at.is_(None))
                            .values(revoked_at=now_utc()))
            audit(self.db, token.user_id, "REFRESH_TOKEN_REUSE", "user", token.user_id)
            self.db.commit()
            raise AppError(401, "SESSION_EXPIRED", "Your session has expired. Please sign in again.")
        user = self.db.get(User, token.user_id)
        if as_utc(token.expires_at) <= now_utc() or not user or not user.active:
            raise AppError(401, "SESSION_EXPIRED", "Your session has expired. Please sign in again.")
        # Conditional update makes concurrent refreshes of the same token race-safe: only one wins.
        won = self.db.execute(update(RefreshToken).where(RefreshToken.id == token.id, RefreshToken.revoked_at.is_(None))
                              .values(revoked_at=now_utc())).rowcount
        if not won:
            self.db.rollback()
            raise AppError(401, "SESSION_EXPIRED", "Your session has expired. Please sign in again.")
        return self.issue(user, token.family_id)

    def revoke(self, raw: str) -> None:
        token = self.db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_secret(raw)))
        if token and token.revoked_at is None:
            self.db.execute(update(RefreshToken).where(RefreshToken.family_id == token.family_id, RefreshToken.revoked_at.is_(None))
                            .values(revoked_at=now_utc()))
            self.db.commit()


class AuthenticationService:
    """Email + password sign-in for business staff and administrators."""

    def __init__(self, db: Session):
        self.db = db

    def authenticate(self, email: str, password: str) -> dict:
        key = f"login:{email.lower()}"
        if ratelimit.count(key) >= settings.login_max_failures:
            raise AppError(429, "RATE_LIMITED", "Too many attempts. Try again in a few minutes.")
        user = self.db.scalar(select(User).where(User.email == email.lower()))
        if not user or user.role == "CUSTOMER" or not user.active or not verify_password(password, user.password_hash):
            ratelimit.hit(key, settings.login_window_seconds)
            raise AppError(401, "INVALID_CREDENTIALS", "Incorrect email or password")
        ratelimit.reset(key)
        audit(self.db, user.id, "LOGIN", "user", user.id)
        return TokenService(self.db).issue(user)


class OtpService:
    """Phone + one-time code sign-in for marketplace customers."""

    def __init__(self, db: Session):
        self.db = db

    def request(self, raw_phone: str) -> dict:
        try:
            phone = normalize_tz_phone(raw_phone)
        except ValueError as exc:
            raise AppError(422, "INVALID_PHONE", str(exc)) from exc
        latest = self.db.scalar(select(OtpChallenge).where(OtpChallenge.phone == phone).order_by(OtpChallenge.created_at.desc()))
        if latest:
            wait = settings.otp_resend_seconds - int((now_utc() - as_utc(latest.created_at)).total_seconds())
            if wait > 0:
                raise AppError(429, "OTP_RESEND_TOO_SOON", "Please wait before requesting another code.", {"retry_after": wait},
                               headers={"Retry-After": str(wait)})
        if ratelimit.hit(f"otp:{phone}", settings.otp_request_window_seconds) > settings.otp_max_requests_per_window:
            raise AppError(429, "RATE_LIMITED", "Too many codes requested. Try again later.")
        code = new_otp_code()
        # Any earlier unconsumed code stops working once a new one is issued.
        self.db.execute(update(OtpChallenge).where(OtpChallenge.phone == phone, OtpChallenge.consumed_at.is_(None))
                        .values(consumed_at=now_utc()))
        self.db.add(OtpChallenge(phone=phone, code_hash=hash_secret(f"{phone}:{code}"),
                                 expires_at=now_utc() + timedelta(seconds=settings.otp_ttl_seconds)))
        self.db.commit()
        self._deliver(phone, code)
        response = {"phone": phone, "expires_in": settings.otp_ttl_seconds, "resend_in": settings.otp_resend_seconds}
        if settings.expose_dev_otp and settings.dev_tools_enabled:
            response["dev_code"] = code
        return response

    def _deliver(self, phone: str, code: str) -> None:
        # settings.sms_provider == "console": development only. The code is logged here and nowhere else.
        log.info("otp_issued", extra={"phone": mask_phone(phone), "dev_code": code if settings.dev_tools_enabled else None})

    def verify(self, raw_phone: str, code: str) -> dict:
        try:
            phone = normalize_tz_phone(raw_phone)
        except ValueError as exc:
            raise AppError(422, "INVALID_PHONE", str(exc)) from exc
        challenge = self.db.scalar(select(OtpChallenge).where(OtpChallenge.phone == phone, OtpChallenge.consumed_at.is_(None))
                                   .order_by(OtpChallenge.created_at.desc()))
        if not challenge or as_utc(challenge.expires_at) <= now_utc():
            raise AppError(400, "OTP_EXPIRED", "This code has expired. Request a new one.")
        if challenge.attempts >= settings.otp_max_attempts:
            raise AppError(429, "OTP_LOCKED", "Too many incorrect attempts. Request a new code.")
        if not constant_time_equals(challenge.code_hash, hash_secret(f"{phone}:{code}")):
            challenge.attempts += 1
            if challenge.attempts >= settings.otp_max_attempts:
                challenge.consumed_at = now_utc()
            self.db.commit()
            remaining = max(settings.otp_max_attempts - challenge.attempts, 0)
            raise AppError(400, "OTP_INVALID", "That code is not correct.", {"attempts_remaining": remaining})
        challenge.consumed_at = now_utc()
        user = self.db.scalar(select(User).where(User.phone == phone))
        is_new = user is None
        if user and user.role != "CUSTOMER":
            raise AppError(403, "FORBIDDEN", "This number belongs to a staff account. Use business sign-in.")
        if user and not user.active:
            raise AppError(403, "ACCOUNT_DISABLED", "This account has been disabled.")
        if is_new:
            user = User(phone=phone, role="CUSTOMER", full_name="")
            self.db.add(user)
            self.db.flush()
            audit(self.db, user.id, "CUSTOMER_REGISTERED", "user", user.id)
        self._link_customer_record(user)
        self.db.commit()
        result = TokenService(self.db).issue(user)
        result["is_new_user"] = is_new or not user.full_name
        return result

    def _link_customer_record(self, user: User) -> None:
        """A walk-in customer a laundry already knows by phone becomes the same person in the marketplace."""
        record = self.db.scalar(select(Customer).where(Customer.phone == user.phone))
        if record is None:
            self.db.add(Customer(user_id=user.id, name=user.full_name or "", phone=user.phone))
        elif record.user_id is None:
            record.user_id = user.id
            if not user.full_name and record.name:
                user.full_name = record.name
