"""``matrix.json``: the traceability matrix of a run, for the UI.

One row per requirement: its URS sentence and value with their citation, the Coverage class
and its reason (the first failing condition of the decision table), the two properties the
LLM judged, each Evidence step with its citation and verdict, and the design facts compared
with the URS value. The shape is ``traceq.runs.schemas.Matrix``, which the API serves.
"""

from __future__ import annotations

from traceq.runs.schemas import (
    AmbiguousValue,
    Cite,
    DesignRow,
    EvidenceStep,
    Matrix,
    MatrixRow,
    NotRead,
    ObservedValue,
)
from traceq.traceability import Ambiguous, Citation, Traceability
from traceq.traceability.coverage import Observed


def _cite(c: Citation) -> Cite:
    return Cite(doc=c.doc, rev=c.rev, page=c.page, quote=c.quote)


def _observed(v: Observed | None) -> ObservedValue | None:
    if isinstance(v, Ambiguous):
        return AmbiguousValue(readings=tuple(v.readings))
    return v


def _row(t: Traceability, rid: str, text: str, source: Citation) -> MatrixRow:
    claim = t.values.get(rid)
    linked = t.linked.get(rid)
    value = None if claim is None else claim.value
    value_citation = None if claim is None else _cite(claim.citation)
    if linked is None:
        return MatrixRow(
            id=rid,
            text=text,
            source=_cite(source),
            value=value,
            value_citation=value_citation,
            coverage=None,
            reason=None,
            site_only=None,
            transport_sensitive=None,
        )
    return MatrixRow(
        id=rid,
        text=text,
        source=_cite(source),
        value=value,
        value_citation=value_citation,
        coverage=linked.coverage.coverage,
        reason=linked.coverage.reason,
        site_only=linked.facts.site_only,
        transport_sensitive=linked.facts.transport_sensitive,
        evidence=tuple(
            EvidenceStep(
                doc=s.protocol.doc,
                rev=s.protocol.rev,
                stage=s.protocol.stage,
                step=s.step,
                test=s.test,
                acceptance=s.acceptance,
                observed=s.observed,
                observed_value=_observed(v.step.observed),
                result=s.result,
                failure=v.failure,
                citation=_cite(s.citation),
            )
            for s, v in zip(linked.steps, linked.coverage.verdicts, strict=True)
        ),
        design=tuple(
            DesignRow(
                doc=d.fact.doc,
                rev=d.fact.rev,
                name=d.name,
                printed=d.printed,
                value=d.fact.value,
                citation=_cite(d.citation),
            )
            for d in linked.rows
        ),
    )


def matrix(t: Traceability) -> Matrix:
    return Matrix(
        requirements=tuple(_row(t, r.id, r.text, r.citation) for r in t.requirements),
        not_read=tuple(
            NotRead(doc_id=d.doc_id, rev=d.rev, format=d.format) for d in t.vendor.not_read
        ),
    )
