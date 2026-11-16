"""Engine, transactions, roles and migrations."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from functools import cache
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import URL, Connection, Engine, create_engine
from sqlalchemy.orm import Session

HERE = Path(__file__).parent
OWNER_ROLE = "traceq_owner"
APP_ROLE = "traceq_app"


@cache
def engine(url: URL) -> Engine:
    """One engine (and connection pool) per database and role."""
    return create_engine(url)


@contextmanager
def transaction(db: Engine) -> Generator[Session]:
    """A session whose work is committed together on success and rolled back on error."""
    with Session(db) as session, session.begin():
        yield session


def ensure_roles(admin: Connection) -> None:
    """Creates the owner and application roles if missing, through a connection whose role
    may create roles.

    Safe to run again and from two sessions at once. The passwords are the role names: the
    server listens on the local machine only (``compose.yaml``) and holds demo data.
    """
    admin.exec_driver_sql((HERE / "roles.sql").read_text(encoding="utf-8"))
    if admin.in_transaction():
        admin.commit()


def upgrade(owner: URL) -> None:
    """Applies the migrations up to the latest, connected as the owner role."""
    config = Config()
    config.set_main_option("script_location", str(HERE / "migrations"))
    config.attributes["url"] = owner
    command.upgrade(config, "head")
