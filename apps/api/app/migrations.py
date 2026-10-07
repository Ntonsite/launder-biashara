from pathlib import Path

from alembic import command
from alembic.config import Config

from .core.config import settings

API_ROOT = Path(__file__).resolve().parent.parent


def alembic_config(url: str | None = None) -> Config:
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", url or settings.database_url)
    return config


def upgrade_to_head(url: str | None = None) -> None:
    command.upgrade(alembic_config(url), "head")
