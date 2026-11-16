"""The TraceQ database: engine, session, server roles and migrations (spec #105).

Postgres holds what humans write. Two roles: ``OWNER_ROLE`` owns the schema and runs the
migrations; the application connects as ``APP_ROLE``, to which the migrations grant only what
it may do. Roles belong to the server, so they are created outside the migrations,
idempotently, and never dropped.
"""

from traceq.db.database import (
    APP_ROLE,
    OWNER_ROLE,
    engine,
    ensure_roles,
    transaction,
    upgrade,
)

__all__ = ["APP_ROLE", "OWNER_ROLE", "engine", "ensure_roles", "transaction", "upgrade"]
