"""PW-001 held-out world data (ticket #200, spec #195): structure only.

PW-001 is held out: its requirement text, values, labels, Evidence and defect locations
must never reach the development session. These tests therefore assert booleans and
counts, and a failure message names ids or counts only, never a value or a sentence.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from traceq_dataset.answer_key import FILES, derive, dump, load_key
from traceq_dataset.corpus import Corpus, build_corpus
from traceq_dataset.render import awaiting_confirmation
from traceq_dataset.schema import (
    CoverageClass,
    DefectType,
    Document,
    Equipment,
    RangeSpec,
    fmt_number,
)
from traceq_dataset.validate import answer_key_problems, missing_text
from traceq_dataset.world import disagreements, load
from traceq_eval.citations import PageTexts
from traceq_eval.oracle import perfect
from traceq_eval.score import score

ROOT = Path(__file__).parents[1]
PW001 = ROOT / "world" / "pw001.yaml"
KEY = ROOT / "answer_key" / "PW-001"


@pytest.fixture(scope="module")
def eq() -> Equipment:
    return load(PW001)


@pytest.fixture(scope="module")
def corpus(eq: Equipment) -> Corpus:
    return build_corpus(eq)


@pytest.fixture(scope="module")
def key(corpus: Corpus) -> dict[str, list[dict[str, Any]]]:
    return derive(corpus)


def test_world_validates_with_nothing_pending_or_unreviewed(eq: Equipment) -> None:
    assert len(eq.pending()) == 0, f"{len(eq.pending())} pending"
    assert [r.id for r in eq.unreviewed()] == []
    assert [i.id for i in eq.unreviewed_results()] == []
    assert not eq.unreviewed_risks()


def test_intended_coverage_is_reproduced(eq: Equipment) -> None:
    """Ids only: a disagreement line would print the classes."""
    assert [line.split(":")[0] for line in disagreements(eq)] == []


def test_counts(eq: Equipment) -> None:
    assert len(eq.requirements) == 36
    counts = Counter(r.intended_coverage for r in eq.requirements)
    others = [c for c in CoverageClass if c is not CoverageClass.CONFLICT]
    short = [c.value for c in others if counts[c] < 4]
    assert short == [], "classes under 4"
    assert counts[CoverageClass.CONFLICT] >= 2, "conflict under 2"


def test_four_defects_of_distinct_types_and_one_ambiguous_value(eq: Equipment) -> None:
    findings = [s.finding for s in eq.scenarios if s.finding]
    ambiguous = [f for f in findings if f.type is DefectType.AMBIGUOUS_VALUE]
    defects = [f for f in findings if f.type is not DefectType.AMBIGUOUS_VALUE]
    assert len(defects) == 4, f"{len(defects)} defects"
    assert len({f.type for f in defects}) == 4, "defect types repeat"
    assert len(ambiguous) == 1, f"{len(ambiguous)} ambiguous findings"


def test_exactly_one_value_reads_two_ways(
    eq: Equipment, key: dict[str, list[dict[str, Any]]]
) -> None:
    assert len(awaiting_confirmation(eq)) == 1
    assert len(key["ambiguous.yaml"]) == 1
    assert all("scenario" in a for a in key["ambiguous.yaml"]), "unplanted ambiguous value"


def test_probes(eq: Equipment, key: dict[str, list[dict[str, Any]]]) -> None:
    """The schema checks each probe's fact is absent; here: about 10% of the items, four
    without Evidence and one without an Acceptance Criterion, every lure located."""
    absent = Counter(p.absent for p in eq.probes)
    assert (absent["evidence"], absent["acceptance"]) == (4, 1)
    assert len(key["probes.yaml"]) == 5
    assert all(p["lures"] for p in key["probes.yaml"])


def test_derived_key_matches_the_documents(
    key: dict[str, list[dict[str, Any]]], corpus: Corpus
) -> None:
    """Required documents match the corpus, values sit on their pages, anchors resolve."""
    problems = answer_key_problems(key, corpus)
    assert len(problems) == 0, f"{len(problems)} answer-key problems"
    unplaced = [f"{doc} rev {rev}" for (doc, rev), r in corpus.rendered.items() if missing_text(r)]
    assert unplaced == []


def test_required_documents_are_the_rendered_package(eq: Equipment, corpus: Corpus) -> None:
    rendered = {doc for doc, _ in corpus.rendered}
    governing = {d.id for d in eq.documents if d.type in Document.GOVERNING_TYPES}
    in_corpus = {d.id for d in eq.required_documents if d.missing is None}
    assert rendered - governing == in_corpus
    missing = Counter(d.missing for d in eq.required_documents if d.missing)
    assert missing == {"expected_gap": 2}
    assert not {"risk_assessment", "dq_report"} & {d.type for d in eq.documents}


def test_matrix_urs_with_one_two_requirement_row(eq: Equipment) -> None:
    (urs,) = [d for d in eq.documents if d.type == "urs"]
    assert urs.layout == "matrix"
    shared = [c for c, n in Counter(r.clause for r in eq.requirements).items() if n > 1]
    assert len(shared) == 1, f"{len(shared)} two-requirement rows"


def test_urs_sentences_state_their_bounds(
    eq: Equipment, key: dict[str, list[dict[str, Any]]]
) -> None:
    """A bound written out in the sentence (``2,0``) must still be the spec's number."""
    texts = {r["id"]: r["text"] for r in key["requirements.yaml"]}
    wrong = []
    for r in eq.requirements:
        if not isinstance(r.spec, RangeSpec):
            continue
        for bound in (r.spec.min, r.spec.max):
            form = re.escape(fmt_number(bound, "id")) if bound is not None else None
            if form and not re.search(rf"(?<![\d.,]){form}(,0+)?(?![\d]|[.,]\d)", texts[r.id]):
                wrong.append(r.id)
    assert wrong == []


def test_units_use_one_canonical_symbol(eq: Equipment) -> None:
    """The scorer compares units after NFKC and casefold only (decisions, Variation)."""
    units = [r.spec.unit for r in eq.requirements if isinstance(r.spec, RangeSpec)]
    assert not [u for u in units if "uS" in u or "ppb" in u or "\N{GREEK SMALL LETTER MU}" in u]


def test_committed_key_is_current(key: dict[str, list[dict[str, Any]]], corpus: Corpus) -> None:
    """Regenerate with: uv run python -m traceq_dataset.answer_key world/pw001.yaml

    File names and row counts only: a diff would print held-out values."""
    committed = {p.name for p in KEY.glob("*.yaml")}
    assert committed == set(FILES), f"{len(committed)} files, expected {len(FILES)}"
    stale = [
        name
        for name, data in key.items()
        if (KEY / name).read_text(encoding="utf-8") != dump(name, data, corpus)
    ]
    assert stale == [], "stale: " + ", ".join(
        f"{name} ({len(key[name])} rows derived)" for name in stale
    )


def test_perfect_submission_passes_every_gate(corpus: Corpus) -> None:
    """The oracle answers the committed key; gate names only on failure."""
    committed = load_key(KEY)
    report = score(perfect(committed, "PW-001"), committed, PageTexts(corpus))
    gates = {name: g for name, g in report["gates"].items() if name != "passed"}
    assert [name for name, g in gates.items() if not g["passed"]] == []
    assert report["gates"]["passed"]
