"""Appending to and reading the Audit Trail."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    MetaData,
    RowMapping,
    Table,
    Text,
    insert,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

type JsonValue = dict[str, Any] | list[Any] | str | int | float | bool | None

_TABLE = Table(
    "audit_trail",
    MetaData(),
    Column("id", BigInteger, primary_key=True),
    Column("at", DateTime(timezone=True)),
    Column("subject", Text),
    Column("issuer", Text),
    Column("name", Text),
    Column("action", Text),
    Column("record_type", Text),
    Column("record_id", Text),
    Column("old_value", JSONB(none_as_null=True)),
    Column("new_value", JSONB(none_as_null=True)),
    Column("reason", Text),
)


@dataclass(frozen=True)
class Actor:
    """Who acted: the token's subject and issuer, and the name shown at the time."""

    subject: str
    issuer: str
    name: str


def actor_of_row(m: RowMapping) -> Actor:
    """The Actor a table row records in its ``subject``, ``issuer`` and ``name`` columns."""
    return Actor(subject=m["subject"], issuer=m["issuer"], name=m["name"])


@dataclass(frozen=True)
class Entry:
    id: int
    at: datetime
    actor: Actor
    action: str
    record_type: str
    record_id: str
    old_value: JsonValue
    new_value: JsonValue
    reason: str | None


def _entry(m: RowMapping) -> Entry:
    return Entry(
        id=m["id"],
        at=m["at"],
        actor=actor_of_row(m),
        action=m["action"],
        record_type=m["record_type"],
        record_id=m["record_id"],
        old_value=m["old_value"],
        new_value=m["new_value"],
        reason=m["reason"],
    )


def append(
    session: Session,
    actor: Actor,
    action: str,
    record_type: str,
    record_id: str,
    *,
    old: JsonValue = None,
    new: JsonValue = None,
    reason: str | None = None,
) -> Entry:
    """Adds an entry in the session's transaction, so it commits with the change it records."""
    row = session.execute(
        insert(_TABLE)
        .values(
            subject=actor.subject,
            issuer=actor.issuer,
            name=actor.name,
            action=action,
            record_type=record_type,
            record_id=record_id,
            old_value=old,
            new_value=new,
            reason=reason,
        )
        .returning(*_TABLE.c)
    )
    return _entry(row.mappings().one())


def entries(session: Session) -> list[Entry]:
    """Every entry, oldest first."""
    rows = session.execute(select(_TABLE).order_by(_TABLE.c.id)).mappings()
    return [_entry(m) for m in rows]
