"""The printed requirement numbers a run missed, and the dispositions on them (spec #247,
"Missed requirement numbers", "Concurrency"; ADR 0012 "Submission").

The missed numbers come from the run's URS completeness check (``completeness.json``, read
through the served-file guard), per URS document and revision; a URS checked
``not_applicable`` has none. A Qualification Engineer records a disposition of each, in a
Protocol in Draft status, as ``not_a_requirement`` or ``not_tested_here`` with a written
justification, and may change it: every disposition is kept, versioned 1, 2, ... per URS
document, revision and number, like a written Test Step, and the latest is in force. A number
without a disposition blocks submission. Unquoted text is shown and needs no disposition, so
it never blocks.

Dispositions belong to one Protocol and do not carry over to a later one. Recording one takes
the per-Protocol lock and checks the status inside it, and has its Audit Trail entry. The
tables keep their first names (``missed_number_answers``): the spec called a disposition an
answer, and the API never names one (``tests/test_api.py``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, cast

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Integer,
    MetaData,
    RowMapping,
    Table,
    Text,
    select,
)
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from traceq import audit
from traceq.assembly import lifecycle
from traceq.assembly.lifecycle import NotFound, Refused
from traceq.runs.api import read_served
from traceq.runs.completeness import COMPLETENESS_FILE
from traceq.runs.schemas import Completeness, UnquotedText

type MissedKind = Literal["not_a_requirement", "not_tested_here"]
"""``not_a_requirement``: the printed number names no requirement (a heading, a reference).
``not_tested_here``: a requirement this Protocol does not test."""

_META = MetaData()
DISPOSITIONS = Table(
    "missed_number_answers",
    _META,
    Column("id", BigInteger, primary_key=True),
    Column("at", DateTime(timezone=True)),
    Column("protocol_id", BigInteger),
    Column("doc", Text),
    Column("rev", Integer),
    Column("number", Text),
    Column("version", Integer),
    Column("kind", Text),
    Column("justification", Text),
    Column("subject", Text),
    Column("issuer", Text),
    Column("name", Text),
)

type Key = tuple[str, int, str]
"""URS document, revision and printed number."""


@dataclass(frozen=True)
class Disposition:
    id: int
    at: datetime
    protocol_id: int
    doc: str
    rev: int
    number: str
    version: int
    kind: MissedKind
    justification: str
    actor: audit.Actor


@dataclass(frozen=True)
class MissedNumber:
    number: str
    page: int
    """The first page it is printed on; shown, not part of the key."""
    dispositions: tuple[Disposition, ...]
    """Every disposition of it in this Protocol, oldest first; the latest is in force."""

    @property
    def disposition(self) -> Disposition | None:
        """The disposition in force."""
        return self.dispositions[-1] if self.dispositions else None

    @property
    def blocking(self) -> bool:
        return not self.dispositions


@dataclass(frozen=True)
class UrsMissed:
    doc: str
    rev: int
    numbers: Literal["checked", "not_applicable"]
    missed: tuple[MissedNumber, ...]
    """Empty for a URS checked ``not_applicable``."""
    unquoted: tuple[UnquotedText, ...]


def check_of(folder: Path | None) -> Completeness | None:
    """The run's URS completeness check; ``None`` for a run written before it existed."""
    path = None if folder is None else folder / COMPLETENESS_FILE
    if path is None or not path.is_file():
        return None
    return Completeness.model_validate(read_served(path))


def _disposition(m: RowMapping) -> Disposition:
    return Disposition(
        id=m["id"],
        at=m["at"],
        protocol_id=m["protocol_id"],
        doc=m["doc"],
        rev=m["rev"],
        number=m["number"],
        version=m["version"],
        kind=cast(MissedKind, m["kind"]),
        justification=m["justification"],
        actor=audit.actor_of_row(m),
    )


def dispositions_of(session: Session, protocol_id: int) -> dict[Key, tuple[Disposition, ...]]:
    """Every disposition of the Protocol per URS document, revision and number, oldest
    first."""
    out: dict[Key, list[Disposition]] = {}
    for m in session.execute(
        select(DISPOSITIONS)
        .where(DISPOSITIONS.c.protocol_id == protocol_id)
        .order_by(DISPOSITIONS.c.version)
    ).mappings():
        d = _disposition(m)
        out.setdefault((d.doc, d.rev, d.number), []).append(d)
    return {k: tuple(v) for k, v in out.items()}


def _missable(check: Completeness | None) -> set[Key]:
    if check is None:
        return set()
    return {(u.doc, u.rev, m.number) for u in check.urs if u.numbers == "checked" for m in u.missed}


def missed_of(
    session: Session, protocol_id: int, check: Completeness | None
) -> list[UrsMissed] | None:
    """Per URS of the run's completeness check, its missed numbers with their dispositions in
    this Protocol and its unquoted text; ``None`` when the check did not run."""
    if check is None:
        return None
    dispositions = dispositions_of(session, protocol_id)
    return [
        UrsMissed(
            doc=u.doc,
            rev=u.rev,
            numbers=u.numbers,
            missed=tuple(
                MissedNumber(m.number, m.page, dispositions.get((u.doc, u.rev, m.number), ()))
                for m in u.missed
            )
            if u.numbers == "checked"
            else (),
            unquoted=u.unquoted,
        )
        for u in check.urs
    ]


def _audit_value(d: Disposition) -> dict[str, Any]:
    return {
        "disposition_id": d.id,
        "protocol_id": d.protocol_id,
        "doc": d.doc,
        "rev": d.rev,
        "number": d.number,
        "version": d.version,
        "kind": d.kind,
        "justification": d.justification,
    }


def dispose(
    session: Session,
    actor: audit.Actor,
    protocol_id: int,
    check: Completeness | None,
    key: Key,
    kind: MissedKind,
    justification: str,
) -> Disposition:
    """Records a disposition of a number the Protocol's run missed; the Protocol must be in
    Draft status. ``check``: the completeness check of the Protocol's run."""
    protocol = lifecycle.locked(
        session,
        protocol_id,
        "draft",
        "a missed number gets a disposition only while it is in Draft status",
    )
    justification = justification.strip()
    if not justification:
        raise Refused("a disposition of a missed number needs a written justification")
    doc, rev, number = key
    if key not in _missable(check):
        raise NotFound(f"run {protocol.run_id} did not miss {number} in {doc} revision {rev}")
    earlier = dispositions_of(session, protocol_id).get(key, ())
    added = _disposition(
        session.execute(
            insert(DISPOSITIONS)
            .values(
                protocol_id=protocol_id,
                doc=doc,
                rev=rev,
                number=number,
                version=len(earlier) + 1,
                kind=kind,
                justification=justification,
                subject=actor.subject,
                issuer=actor.issuer,
                name=actor.name,
            )
            .returning(*DISPOSITIONS.c)
        )
        .mappings()
        .one()
    )
    audit.append(
        session,
        actor,
        "missed number disposition recorded",
        "missed_number",
        f"{protocol_id}/{doc}/{rev}/{number}",
        old=None if not earlier else _audit_value(earlier[-1]),
        new=_audit_value(added),
    )
    return added
