"""Proposal identity: subject keys and content hashes (spec #105, "Proposal identity").

A Proposal's **subject key** says what it is about; its **content** is what a decision on it
rests on. Both follow the spec's table:

- Coverage row: key = Equipment, requirement id. Content = the URS document and revision the
  requirement is printed in, Coverage class, reason, required value, the two judged
  properties, and per Evidence step and design row the document, revision, step or row name,
  the value read, and (for a step) result and failure.
- Check Finding: key = Equipment, layer, type, document, and its citations as a set.
  Content = detail text, cited site rule.
- AI Finding: key = Equipment, layer, type, and its citations as a set. Content = detail text.
- Draft finding (a Check Finding, layer Rule, on the Protocol Draft of a Review Package run,
  spec #196): key = Equipment, layer, type, draft document and revision, the Test Step id (or
  the traceability row's requirement id for ``requirement_not_tested``) and the requirement it
  was compared with, since a Test Step the table lists under two requirements gives a finding
  for each. Content = detail text, the rule (its type) and the values compared (AC and URS
  limit as parsed). No quote text enters either: a re-run whose quote differs only in length
  is the same Proposal with the same content, while a change in a compared value asks again.

Wording is left out of Coverage content (the model's paraphrase, every quote), and nothing that
only describes the run enters a key or a hash (run id, time, model, prompt hash). Two Proposals
of one run with the same key are told apart by their order within that key (``ordinal``).
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from typing import Any, Literal

from traceq.runs.schemas import (
    AiFinding,
    CheckFinding,
    Cite,
    DraftCheckFinding,
    Findings,
    Matrix,
    MatrixRow,
    PrintedRead,
    ProtocolDraft,
)

type Kind = Literal["coverage", "check", "ai", "draft"]
"""``draft``: a Check Finding on the Protocol Draft under review, kept apart from the
Equipment's Check Findings."""
type JsonObject = dict[str, Any]


@dataclass(frozen=True)
class Proposed:
    """One Proposal as a run proposed it."""

    kind: Kind
    subject: JsonObject
    subject_hash: str
    ordinal: int
    """Its order among the run's Proposals with the same subject key, from 0."""
    content_hash: str
    proposed: JsonObject
    """The item as written in the run's file."""
    requirement: str | None
    """For a Coverage row: the requirement id."""
    position: int | None
    """For a finding: its position in its layer's list in ``findings.json``; for a draft
    finding, in the findings of ``protocol_draft.json``."""


def _canonical(data: Any) -> str:
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def digest(data: Any) -> str:
    """The SHA-256 of the canonical JSON of ``data``."""
    return hashlib.sha256(_canonical(data).encode("utf-8")).hexdigest()


def _as_set(items: list[JsonObject]) -> list[JsonObject]:
    """Order and repetition removed: equal sets give equal lists."""
    return [json.loads(s) for s in sorted({_canonical(i) for i in items})]


def _citations(cites: tuple[Cite, ...]) -> list[JsonObject]:
    return _as_set([c.model_dump(mode="json") for c in cites])


def _coverage_content(row: MatrixRow) -> JsonObject:
    def dump(v: Any) -> Any:
        return None if v is None else v.model_dump(mode="json")

    return {
        "urs": {"doc": row.source.doc, "rev": row.source.rev},
        "coverage": row.coverage,
        "reason": row.reason,
        "value": dump(row.value),
        "site_only": row.site_only,
        "transport_sensitive": row.transport_sensitive,
        "evidence": _as_set(
            [
                {
                    "doc": e.doc,
                    "rev": e.rev,
                    "step": e.step,
                    "value": dump(e.observed_value),
                    "result": e.result,
                    "failure": e.failure,
                }
                for e in row.evidence
            ]
        ),
        "design": _as_set(
            [
                {"doc": d.doc, "rev": d.rev, "name": d.name, "value": dump(d.value)}
                for d in row.design
            ]
        ),
    }


def _check(equipment: str, f: CheckFinding) -> tuple[JsonObject, JsonObject]:
    subject = {
        "equipment": equipment,
        "layer": "check",
        "type": f.type,
        "doc": f.doc,
        "citations": _citations(f.citations),
    }
    rule = None if f.rule is None else f.rule.model_dump(mode="json")
    return subject, {"detail": f.detail, "rule": rule}


def _ai(equipment: str, f: AiFinding) -> tuple[JsonObject, JsonObject]:
    subject = {
        "equipment": equipment,
        "layer": "ai",
        "type": f.type,
        "citations": _citations(f.citations),
    }
    return subject, {"detail": f.detail}


def _read(v: PrintedRead | None) -> JsonObject | None:
    return None if v is None else v.model_dump(mode="json", exclude_none=True)


def _draft(
    equipment: str, draft: ProtocolDraft, f: DraftCheckFinding
) -> tuple[JsonObject, JsonObject]:
    where = {"test_step": f.test_step} if f.test_step is not None else {"row": f.row}
    subject = {
        "equipment": equipment,
        "layer": f.layer,
        "type": f.type,
        "doc": draft.document.doc_id,
        "rev": draft.document.rev,
        **where,
        "requirement": f.requirement,
    }
    content = {
        "detail": f.detail,
        "rule": f.type,
        "ac": _read(f.ac),
        "urs_limit": _read(f.urs_limit),
    }
    return subject, content


def proposals_of(
    equipment: str, matrix: Matrix, findings: Findings, draft: ProtocolDraft | None = None
) -> list[Proposed]:
    """Every Coverage row, Check Finding and AI Finding of a run, then the findings on its
    Protocol Draft (a Review Package run), in file order. Drafted Test Steps are Proposals too
    but not imported in this slice."""
    seen: Counter[str] = Counter()
    out: list[Proposed] = []

    def add(
        kind: Kind,
        subject: JsonObject,
        content: JsonObject,
        item: JsonObject,
        requirement: str | None = None,
        position: int | None = None,
    ) -> None:
        key = {"kind": kind, **subject}
        h = digest(key)
        out.append(
            Proposed(
                kind=kind,
                subject=key,
                subject_hash=h,
                ordinal=seen[h],
                content_hash=digest(content),
                proposed=item,
                requirement=requirement,
                position=position,
            )
        )
        seen[h] += 1

    for row in matrix.requirements:
        subject = {"equipment": equipment, "requirement": row.id}
        add(
            "coverage",
            subject,
            _coverage_content(row),
            row.model_dump(mode="json"),
            requirement=row.id,
        )
    for i, c in enumerate(findings.check_findings):
        add("check", *_check(equipment, c), c.model_dump(mode="json"), position=i)
    for i, a in enumerate(findings.ai_findings):
        add("ai", *_ai(equipment, a), a.model_dump(mode="json"), position=i)
    if draft is not None:
        for i, d in enumerate(draft.findings):
            add("draft", *_draft(equipment, draft, d), d.model_dump(mode="json"), position=i)
    return out
