"""Pre-review of a corpus: read the governing documents and the records, then apply the
rules (Check Findings), then the LLM on what the rules cannot judge (AI Findings), and
compare the VMP's required documents with the corpus.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from traceq.ai import LLM
from traceq.documents import Corpus, CorpusDocument
from traceq.review.ai_findings import AiFinding, ai_review
from traceq.review.facts import Record, RequiredDocument
from traceq.review.governing import Governing, missing_documents, read_governing
from traceq.review.records import read_records
from traceq.review.rules import CheckFinding, check
from traceq.traceability import Dropped, Traceability


@dataclass
class Review:
    governing: Governing = field(default_factory=Governing)
    records: list[Record] = field(default_factory=list[Record])
    findings: list[CheckFinding] = field(default_factory=list[CheckFinding])
    ai_findings: list[AiFinding] = field(default_factory=list[AiFinding])
    missing: list[RequiredDocument] = field(default_factory=list[RequiredDocument])
    dropped: list[Dropped] = field(default_factory=list[Dropped])
    not_read: list[CorpusDocument] = field(default_factory=list[CorpusDocument])


def review(corpus: Corpus, llm: LLM, traced: Traceability) -> Review:
    out = Review()
    out.governing = read_governing(corpus, llm, out.dropped)
    out.records, out.not_read = read_records(corpus, llm, out.dropped)
    out.findings = check(out.records, traced.vendor.steps, out.governing.rules)
    out.ai_findings = ai_review(corpus, llm, out.dropped)
    out.missing = missing_documents(out.governing.required, corpus)
    return out
