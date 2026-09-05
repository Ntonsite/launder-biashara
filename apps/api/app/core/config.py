import os
from dataclasses import dataclass

@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./launder.db")
    jwt_secret: str = os.getenv("JWT_SECRET", "local-demo-secret-change-in-production")
    jwt_algorithm: str = "HS256"
    access_token_hours: int = 8
    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")

settings = Settings()
