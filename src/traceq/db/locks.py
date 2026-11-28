"""Advisory locks several modules share (they sit here, below them all, so none imports another
for a lock)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

EQUIPMENT_LOCK_NS = 5


def lock_equipment(session: Session, equipment: str) -> None:
    """Takes the Equipment's lock until the transaction ends: whoever writes its document
    revisions (an import registering a run) holds it, and whoever must not read a revision
    half-written, or miss one, waits for it."""
    session.execute(select(func.pg_advisory_xact_lock(EQUIPMENT_LOCK_NS, func.hashtext(equipment))))
