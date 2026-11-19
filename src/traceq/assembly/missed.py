"""The printed requirement numbers a run missed, and the answers on them (spec #247, "Missed
requirement numbers", "Concurrency"; ADR 0012 "Submission").

The missed numbers come from the run's URS completeness check (``completeness.json``), per URS
document and revision; a URS checked ``not_applicable`` has none. A Qualification Engineer
answers each, in a Protocol in Draft status, as ``not_a_requirement`` or ``not_tested_here``
with a written justification, and may change the answer: every answer is kept, numbered 1,
2, ... per URS document, revision and number, and the latest counts. A number without an
answer blocks submission. Unquoted text is shown and never answered, so it never blocks.

Answers belong to one Protocol and do not carry over to a later one. Every answer takes the
per-Protocol lock and checks the status inside it, and has its Audit Trail entry.
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
from traceq.assembly.lifecycle import Conflict, NotFound, Refused
from traceq.runs.completeness import COMPLETENESS_FILE
from traceq.runs.schemas import Completeness, UnquotedText

type MissedKind = Literal["not_a_requirement", "not_tested_here"]
"""``not_a_requirement``: the printed number names no requirement (a heading, a reference).
``not_tested_here``: a requirement this Protocol does not test."""

_META = MetaData()
ANSWERS = Table(
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
class Answer:
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
    answers: tuple[Answer, ...]
    """Every answer on it in this Protocol, oldest first; the latest counts."""

    @property
    def answer(self) -> Answer | None:
        return self.answers[-1] if self.answers else None

    @property
    def blocking(self) -> bool:
        return not self.answers


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
    return Completeness.model_validate_json(path.read_text(encoding="utf-8"))


def _answer(m: RowMapping) -> Answer:
    return Answer(
        id=m["id"],
        at=m["at"],
        protocol_id=m["protocol_id"],
        doc=m["doc"],
        rev=m["rev"],
        number=m["number"],
        version=m["version"],
        kind=cast(MissedKind, m["kind"]),
        justification=m["justification"],
        actor=audit.Actor(subject=m["subject"], issuer=m["issuer"], name=m["name"]),
    )


def answers_of(session: Session, protocol_id: int) -> dict[Key, tuple[Answer, ...]]:
    """Every answer of the Protocol per URS document, revision and number, oldest first."""
    out: dict[Key, list[Answer]] = {}
    for m in session.execute(
        select(ANSWERS).where(ANSWERS.c.protocol_id == protocol_id).order_by(ANSWERS.c.version)
    ).mappings():
        a = _answer(m)
        out.setdefault((a.doc, a.rev, a.number), []).append(a)
    return {k: tuple(v) for k, v in out.items()}


def _missable(check: Completeness | None) -> set[Key]:
    if check is None:
        return set()
    return {(u.doc, u.rev, m.number) for u in check.urs if u.numbers == "checked" for m in u.missed}


def missed_of(
    session: Session, protocol_id: int, check: Completeness | None
) -> list[UrsMissed] | None:
    """Per URS of the run's completeness check, its missed numbers with their answers in this
    Protocol and its unquoted text; ``None`` when the check did not run."""
    if check is None:
        return None
    answers = answers_of(session, protocol_id)
    return [
        UrsMissed(
            doc=u.doc,
            rev=u.rev,
            numbers=u.numbers,
            missed=tuple(
                MissedNumber(m.number, m.page, answers.get((u.doc, u.rev, m.number), ()))
                for m in u.missed
            )
            if u.numbers == "checked"
            else (),
            unquoted=u.unquoted,
        )
        for u in check.urs
    ]


def _audit_value(a: Answer) -> dict[str, Any]:
    return {
        "answer_id": a.id,
        "protocol_id": a.protocol_id,
        "doc": a.doc,
        "rev": a.rev,
        "number": a.number,
        "version": a.version,
        "kind": a.kind,
        "justification": a.justification,
    }


def answer(
    session: Session,
    actor: audit.Actor,
    protocol_id: int,
    check: Completeness | None,
    key: Key,
    kind: MissedKind,
    justification: str,
) -> Answer:
    """Adds an answer on a number the Protocol's run missed; the Protocol must be in Draft
    status. ``check``: the completeness check of the Protocol's run."""
    justification = justification.strip()
    if not justification:
        raise Refused("an answer on a missed number needs a written justification")
    lifecycle.lock_protocol(session, protocol_id)
    protocol = lifecycle.get(session, protocol_id)
    if protocol is None:
        raise NotFound(f"no Protocol {protocol_id}")
    if protocol.status != "draft":
        raise Conflict(
            f"Protocol {protocol_id} is {protocol.status}: missed numbers are answered only"
            " while it is in Draft status"
        )
    doc, rev, number = key
    if key not in _missable(check):
        raise NotFound(f"run {protocol.run_id} did not miss {number} in {doc} revision {rev}")
    earlier = answers_of(session, protocol_id).get(key, ())
    added = _answer(
        session.execute(
            insert(ANSWERS)
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
            .returning(*ANSWERS.c)
        )
        .mappings()
        .one()
    )
    audit.append(
        session,
        actor,
        "missed number answered",
        "missed_number",
        f"{protocol_id}/{doc}/{rev}/{number}",
        old=None if not earlier else _audit_value(earlier[-1]),
        new=_audit_value(added),
    )
    return added
