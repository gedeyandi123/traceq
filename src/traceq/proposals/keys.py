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
  spec #196, #375): key = Equipment, layer, type, draft document id (not its revision, so a
  finding is the same finding across revisions), the Test Step id (or the traceability row's
  requirement id for ``requirement_not_tested``), the requirement it was compared with (a
  Test Step the table lists under two requirements gives a finding for each) and the cited
  locations (document and page of each citation, no revision, no quote text), so two findings
  of one Test Step and type are told apart by where they cite, not by order; only two findings
  citing the same pages fall back to their order. Content = detail text, the rule (its type),
  the values compared (AC, URS limit, capability as parsed) and what the finding rests on: the
  Test Step as read (the requirements its header prints, its Acceptance Criterion as printed
  and as parsed) and its requirement mapping (the requirements the table traces it to), or
  for a table row its requirement and Test Step ids. No quote text enters either: a re-run
  whose quote differs only in length is the same Proposal with the same content, while a
  change in a Test Step, its mapping or its criterion asks again.
- Draft Test Step (``draft_step``) and its Acceptance Criterion (``draft_criterion``), of the
  Protocol Draft of a Review Package run (spec #375, S4a1): key = Equipment, draft document id
  (not its revision), the Test Step id. Content = the requirements the draft's traceability
  table maps the step to (the mapping), and for the step its header requirements, description,
  method, instrument and why the read was dropped; for the criterion the AC as printed, as
  parsed and the page it cites (no quote text, no revision). A change of the step, of its
  mapping or of its criterion asks again (ADR 0012, "Binding to content").
- Drafted Test Step (``drafts.json``, spec #247): key = Equipment, requirement id. Content =
  the URS document and revision the requirement is printed in, description, method,
  instrument, the AC value, the AC citation's document, revision and page (no quote text) and
  the AC flag. Its wording is in the content on purpose: the text is what a human accepts, so
  a re-run that words a draft differently asks again.

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
    DraftAcceptance,
    DraftCheckFinding,
    DraftCriterionProposal,
    DraftedTestStep,
    DraftedTestSteps,
    DraftStepProposal,
    DraftTestStep,
    Findings,
    Matrix,
    MatrixRow,
    PrintedRead,
    ProtocolDraft,
)

type Kind = Literal[
    "coverage", "check", "ai", "draft", "test_step", "draft_step", "draft_criterion"
]
"""``draft``: a Check Finding on the Protocol Draft under review, kept apart from the
Equipment's Check Findings. ``test_step``: an IQ/OQ Test Step the run drafted.
``draft_step`` and ``draft_criterion``: a Test Step the site's Protocol Draft prints and its
Acceptance Criterion, for a Protocol started from the draft."""
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
    """For a Coverage row or a drafted Test Step: the requirement id."""
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


def _locations(cites: tuple[Cite, ...]) -> list[JsonObject]:
    """Where a finding cites, as a set: document and page of each citation. The revision and
    the quote are left out, so a finding keeps its identity across draft revisions and re-runs."""
    return _as_set([{"doc": c.doc, "page": c.page} for c in cites])


def _rests_on(draft: ProtocolDraft, f: DraftCheckFinding) -> JsonObject:
    """What a decision on a draft finding rests on besides the finding's own values: the Test
    Step as read, its Acceptance Criterion and its requirement mapping, or the table row."""
    if f.test_step is not None:
        step = next((s for s in draft.test_steps if s.id == f.test_step), None)
        if step is None:
            return {"test_step": f.test_step}
        ac = step.acceptance
        return {
            "test_step": step.id,
            "header_requirements": list(step.requirements),
            "acceptance": None if ac is None else {"printed": ac.printed, "value": _read(ac.value)},
            "mapped_to": [t.requirement for t in step.traced],
        }
    row = next((r for r in draft.trace_rows if r.requirement == f.row), None)
    if row is None:
        return {"row": f.row}
    return {"row": row.requirement, "test_steps": list(row.test_steps)}


def _draft(
    equipment: str, draft: ProtocolDraft, f: DraftCheckFinding
) -> tuple[JsonObject, JsonObject]:
    where = {"test_step": f.test_step} if f.test_step is not None else {"row": f.row}
    subject = {
        "equipment": equipment,
        "layer": f.layer,
        "type": f.type,
        "doc": draft.document.doc_id,
        **where,
        "requirement": f.requirement,
        "cited": _locations(f.citations),
    }
    content = {
        "detail": f.detail,
        "rule": f.type,
        "ac": _read(f.ac),
        "urs_limit": _read(f.urs_limit),
        **({"capability": _read(f.capability)} if f.capability is not None else {}),
        "rests_on": _rests_on(draft, f),
    }
    return subject, content


def _draft_step(
    equipment: str, draft: ProtocolDraft, s: DraftTestStep
) -> tuple[JsonObject, JsonObject, JsonObject]:
    """The subject, content and stored payload of a draft Test Step's Proposal."""
    mapped = tuple(t.requirement for t in s.traced)
    subject = {"equipment": equipment, "doc": draft.document.doc_id, "test_step": s.id}
    content = {
        "header_requirements": list(s.requirements),
        "mapped_to": list(mapped),
        "description": s.description,
        "method": s.method,
        "instrument": s.instrument,
        "not_read": s.not_read,
    }
    payload = DraftStepProposal(
        document=draft.document,
        id=s.id,
        requirements=s.requirements,
        mapped_to=mapped,
        description=s.description,
        method=s.method,
        instrument=s.instrument,
        not_read=s.not_read,
    )
    return subject, content, payload.model_dump(mode="json")


def _draft_criterion(
    equipment: str, draft: ProtocolDraft, s: DraftTestStep, ac: DraftAcceptance
) -> tuple[JsonObject, JsonObject, JsonObject]:
    mapped = tuple(t.requirement for t in s.traced)
    subject = {"equipment": equipment, "doc": draft.document.doc_id, "test_step": s.id}
    content = {
        "mapped_to": list(mapped),
        "printed": ac.printed,
        "value": _read(ac.value),
        "cited": _locations((ac.citation,)),
    }
    payload = DraftCriterionProposal(
        document=draft.document,
        id=s.id,
        mapped_to=mapped,
        printed=ac.printed,
        value=ac.value,
        citation=ac.citation,
    )
    return subject, content, payload.model_dump(mode="json")


def _test_step(s: DraftedTestStep) -> JsonObject:
    cite = s.acceptance_citation
    return {
        "urs": {"doc": s.source.doc, "rev": s.source.rev},
        "description": s.description,
        "method": s.method,
        "instrument": s.instrument,
        "acceptance": None if s.acceptance is None else s.acceptance.model_dump(mode="json"),
        "acceptance_citation": None
        if cite is None
        else {"doc": cite.doc, "rev": cite.rev, "page": cite.page},
        "acceptance_flag": s.acceptance_flag,
    }


def proposals_of(
    equipment: str,
    matrix: Matrix,
    findings: Findings,
    draft: ProtocolDraft | None = None,
    drafted: DraftedTestSteps | None = None,
) -> list[Proposed]:
    """Every Coverage row, Check Finding and AI Finding of a run, then the findings on its
    Protocol Draft (a Review Package run), then its drafted Test Steps, in file order."""
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
    if draft is not None:
        for i, step in enumerate(draft.test_steps):
            # A step the table maps to exactly one requirement is that requirement's; any
            # other is told apart by its place in the draft (the table holds one or the other).
            single = step.traced[0].requirement if len(step.traced) == 1 else None
            place = None if single is not None else i
            add("draft_step", *_draft_step(equipment, draft, step), single, place)
            if step.acceptance is not None:
                added = _draft_criterion(equipment, draft, step, step.acceptance)
                add("draft_criterion", *added, single, place)
    if drafted is not None:
        for s in drafted.test_steps:
            add(
                "test_step",
                {"equipment": equipment, "requirement": s.requirement},
                _test_step(s),
                s.model_dump(mode="json"),
                requirement=s.requirement,
            )
    return out
