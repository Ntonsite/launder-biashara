from functools import cached_property
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

INSECURE_DEFAULT_SECRET = "local-demo-secret-change-in-production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    database_url: str = "sqlite:///./launder_dev.db"
    redis_url: str | None = None
    jwt_secret: str = INSECURE_DEFAULT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 30
    refresh_token_days: int = 30
    cors_origins_csv: str = "http://localhost:5173,http://127.0.0.1:5173"
    timezone: str = "Africa/Dar_es_Salaam"
    # Runs migrations + idempotent demo seed on startup. Never enable in production.
    auto_seed: bool = True
    # OTP delivery: "console" logs the code (development only); a real SMS provider is Phase 2.
    sms_provider: Literal["console"] = "console"
    expose_dev_otp: bool = True
    otp_ttl_seconds: int = 300
    otp_max_attempts: int = 5
    otp_resend_seconds: int = 60
    otp_max_requests_per_window: int = 5
    otp_request_window_seconds: int = 900
    login_max_failures: int = 8
    login_window_seconds: int = 900
    # Mobile money: "sandbox" never moves money; a provider integration is required for production.
    payment_provider: Literal["sandbox"] = "sandbox"
    payment_webhook_secret: str = "sandbox-webhook-secret"
    public_base_url: str = "http://127.0.0.1:8000"
    default_commission_rate: str = "5.00"

    @model_validator(mode="after")
    def _production_guard(self):
        if self.app_env == "production":
            if self.jwt_secret == INSECURE_DEFAULT_SECRET or len(self.jwt_secret) < 32:
                raise ValueError("JWT_SECRET must be set to a strong value in production")
            if self.auto_seed or self.expose_dev_otp:
                raise ValueError("AUTO_SEED and EXPOSE_DEV_OTP must be false in production")
        return self

    @cached_property
    def cors_origins(self) -> list[str]:
        return [x.strip() for x in self.cors_origins_csv.split(",") if x.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def dev_tools_enabled(self) -> bool:
        return self.app_env in ("development", "test")


settings = Settings()
