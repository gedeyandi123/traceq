"""``findings.json``: the Pre-review of a run, for the UI.

Check Findings (layer ``check``, no model trace), each with its citations and, for a site
rule, the SOP sentence that sets it; AI Findings (layer ``ai``), kept apart, each with its
verified citations and what an audit of an AI Finding needs (ADR 0002): the documents and
revisions it cites, model, prompt hash, time and the reviewer's action, ``pending`` until a
write feature lets a human accept, edit or reject it; the documents the VMP requires for
the Equipment, with the annex row cited, and which of them the corpus lacks; the site rules
read from the SOP.
"""

from __future__ import annotations

from traceq.review import Review
from traceq.runs.schemas import (
    AiFinding,
    CheckFinding,
    Cite,
    Findings,
    GoverningDocument,
    MissingDocument,
    RequiredDocument,
    SiteRuleCite,
    Source,
)
from traceq.traceability import Citation


def _cite(c: Citation) -> Cite:
    return Cite(doc=c.doc, rev=c.rev, page=c.page, quote=c.quote)


def findings(r: Review, *, model: str, prompt: str, created: str) -> Findings:
    missing = {d.doc_id for d in r.missing}
    return Findings(
        check_findings=tuple(
            CheckFinding(
                layer="check",
                type=f.type,
                doc=f.doc,
                detail=f.detail,
                citations=tuple(_cite(c) for c in f.citations),
                rule=None if f.rule is None else _cite(f.rule),
            )
            for f in r.findings
        ),
        ai_findings=tuple(
            AiFinding(
                layer="ai",
                type=f.type,
                detail=f.detail,
                citations=tuple(_cite(c) for c in f.citations),
                sources=tuple(
                    Source(doc=doc, rev=rev)
                    for doc, rev in dict.fromkeys((c.doc, c.rev) for c in f.citations)
                ),
                model=model,
                prompt=prompt,
                created=created,
                reviewer_action="pending",
            )
            for f in r.ai_findings
        ),
        required_documents=tuple(
            RequiredDocument(
                doc_id=d.doc_id,
                type=d.type,
                stage=d.stage,
                in_corpus=d.doc_id not in missing,
                citation=_cite(d.citation),
            )
            for d in r.governing.required
        ),
        missing_documents=tuple(
            MissingDocument(doc_id=d.doc_id, type=d.type, stage=d.stage, citation=_cite(d.citation))
            for d in r.missing
        ),
        site_rules=tuple(
            SiteRuleCite(rule=k, citation=_cite(c)) for k, c in r.governing.rules.items()
        ),
        governing_documents=tuple(
            GoverningDocument(doc_id=d.doc_id, rev=d.rev) for d in r.governing.read
        ),
    )
