"""``protocol_draft.json``: the Protocol Draft of a Review Package run, as read and judged (spec
#196, "Outputs").

One row per Test Step read, in draft order: the requirement ids its header prints, its
Acceptance Criterion as printed with the value code read from it and its citation, and for
each requirement the draft's traceability table lists it under: the URS limit (read from that
requirement's verified URS citation, with the citation, or why it was not parsed), whether
the AC deviates from it or why it was not compared, and the comparators available (the vendor
facts of the requirement's matrix row by document; empty: none). Then whether the row was
compared at all (why not), the traceability rows read, each with its citation, and the draft's
Check Findings (layer Rule) with the values they compared. What the citation check dropped
is in ``run.json``; a Test Step the draft prints whose reading it dropped is also a row here,
in draft order, marked not read with the reason. ``vendor_documents`` names the vendor
documents (datasheets, FAT, SAT) a comparator may come from, so the page can say "none" for
each document without a fact.
"""

from __future__ import annotations

from typing import Literal

from traceq.documents import Corpus
from traceq.review.draft import (
    Comparator,
    DraftReading,
    DraftRow,
    Read,
    StepNotRead,
    in_draft_order,
)
from traceq.review.draft_rules import DraftFinding
from traceq.runs.schemas import (
    AmbiguousValue,
    Cite,
    DraftAcceptance,
    DraftCheckFinding,
    DraftComparator,
    DraftDocument,
    DraftTestStep,
    DraftTraced,
    DraftTraceRow,
    PrintedRead,
    ProtocolDraft,
    VendorDocument,
    VendorFactCite,
)
from traceq.runs.submission import DraftStep, Finding, cite
from traceq.traceability import Ambiguous, Citation

DRAFT_FILE = "protocol_draft.json"
_VENDOR: tuple[tuple[str, Literal["datasheet", "FAT", "SAT"]], ...] = (
    ("datasheet", "datasheet"),
    ("fat", "FAT"),
    ("sat", "SAT"),
)


def _cite(c: Citation) -> Cite:
    return Cite(doc=c.doc, rev=c.rev, page=c.page, quote=c.quote)


def _value(v: Read) -> PrintedRead | None:
    if isinstance(v, Ambiguous):
        return AmbiguousValue(readings=tuple(v.readings))
    return v


def _comparator(c: Comparator) -> DraftComparator:
    return DraftComparator(
        doc=c.doc,
        rev=c.rev,
        kind=c.kind,
        facts=tuple(
            VendorFactCite(name=f.name, printed=f.printed, citation=_cite(f.citation))
            for f in c.facts
        ),
    )


def _finding(f: DraftFinding) -> DraftCheckFinding:
    return DraftCheckFinding(
        type=f.type,
        layer="rule",
        test_step=f.test_step,
        row=f.row,
        requirement=f.requirement,
        detail=f.detail,
        ac=_value(f.ac),
        urs_limit=_value(f.urs),
        citations=tuple(_cite(c) for c in f.citations),
    )


def _not_read(s: StepNotRead) -> DraftTestStep:
    return DraftTestStep(
        id=s.id,
        requirements=(),
        acceptance=None,
        not_read=s.reason,
        traced=(),
        compared=False,
        not_compared=None,
    )


def vendor_documents(corpus: Corpus) -> tuple[VendorDocument, ...]:
    """The current datasheets, FAT and SAT protocols of the run's corpus, in that order."""
    return tuple(
        VendorDocument(doc=d.doc_id, rev=d.rev, kind=kind)
        for doc_type, kind in _VENDOR
        for d in corpus.current(doc_type)
    )


def protocol_draft(
    package: str,
    reading: DraftReading,
    rows: list[DraftRow],
    findings: list[DraftFinding],
    vendor_documents: tuple[VendorDocument, ...] = (),
) -> ProtocolDraft:
    doc = reading.doc
    return ProtocolDraft(
        package=package,
        document=DraftDocument(doc_id=doc.doc_id, rev=doc.rev, sha256=doc.sha256),
        test_steps=tuple(
            _not_read(r)
            if isinstance(r, StepNotRead)
            else DraftTestStep(
                id=r.step.id,
                requirements=r.step.requirements,
                acceptance=DraftAcceptance(
                    printed=r.step.printed,
                    value=_value(r.step.value),
                    citation=_cite(r.step.citation),
                ),
                traced=tuple(
                    DraftTraced(
                        requirement=c.urs.requirement,
                        urs_limit=_value(c.urs.value),
                        citation=None if c.urs.citation is None else _cite(c.urs.citation),
                        not_parsed=c.urs.not_parsed,
                        compared=c.not_compared is None,
                        deviates=c.deviates,
                        not_compared=c.not_compared,
                        comparators=tuple(_comparator(x) for x in c.comparators),
                    )
                    for c in r.traced
                ),
                compared=r.not_compared is None,
                not_compared=r.not_compared,
            )
            for r in in_draft_order(reading, rows)
        ),
        trace_rows=tuple(
            DraftTraceRow(requirement=t.requirement, test_steps=t.steps, citation=_cite(t.citation))
            for t in reading.rows
        ),
        findings=tuple(_finding(f) for f in findings),
        vendor_documents=vendor_documents,
    )


def draft_steps(rows: list[DraftRow]) -> tuple[DraftStep, ...]:
    """The submission's ``draft_steps``: the AC value only when code read one from the print
    (an ambiguous or unknown form leaves it empty), always with its verified citation."""
    out: list[DraftStep] = []
    for r in rows:
        v = r.step.value
        out.append(
            DraftStep(
                id=r.step.id,
                acceptance=None if v is None or isinstance(v, Ambiguous) else v,
                acceptance_citation=cite(r.step.citation),
                compared=r.not_compared is None,
                not_compared=r.not_compared,
            )
        )
    return tuple(out)


def draft_findings_out(findings: list[DraftFinding]) -> tuple[Finding, ...]:
    """The draft's findings in ``submission.json``: each with its Test Step id or table row."""
    return tuple(
        Finding(
            type=f.type,
            detail=f.detail,
            citations=tuple(cite(c) for c in f.citations),
            test_step=f.test_step,
            row=f.row,
        )
        for f in findings
    )
