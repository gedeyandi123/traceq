"""The scorer reads a Review Package key through ``key_at_revision`` (spec #375, ticket S2a).

A 0.2.0 key lists the draft revisions each entry is present in; a run over revision ``r`` is
graded on the key as it reads at ``r``. Without this, revision 0 would be scored against the
defect that only revision 1 has (D-TP201OQ-014) and revision 1 against the ones it fixed.
0.1.0's key has no ``revisions`` and reads the same at revision 0, so its score does not move.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from traceq_dataset.answer_key import load_key
from traceq_dataset.corpus import Corpus
from traceq_dataset.review_package import (
    load_package,
    load_package_key,
    package_key_dir,
    render_draft,
)
from traceq_eval import __main__ as cli
from traceq_eval.citations import PageTexts
from traceq_eval.oracle import perfect_review
from traceq_eval.score import ReviewPackage, score

ROOT = Path(__file__).parents[1]
WORLD = ROOT / "world" / "tp201-oq-draft-0.2.0.yaml"
WORLD_0_1_0 = ROOT / "world" / "tp201-oq-draft.yaml"
TP201 = ROOT / "world" / "tp201.yaml"
KEY_DIR = package_key_dir(ROOT / "answer_key", "TP-201-OQ-draft", "0.2.0")
TP201_KEY = ROOT / "answer_key" / "TP-201"


@pytest.fixture(scope="module")
def corpus(tp201_corpus: Corpus) -> Corpus:
    return tp201_corpus


def _review(corpus: Corpus, rev: int) -> ReviewPackage:
    package = load_package(WORLD)
    return ReviewPackage.of(
        package, render_draft(package, corpus.eq, rev), load_package_key(KEY_DIR)
    )


def test_revision_0_is_graded_on_the_key_as_it_reads_at_revision_0(corpus: Corpus) -> None:
    review = _review(corpus, 0)
    defects = review.key["defects.yaml"]
    assert len(defects) == 13
    assert "D-TP201OQ-014" not in {d["id"] for d in defects}  # new in revision 1
    assert len(review.key["test_steps.yaml"]) == 26
    assert len(review.key["clean_traps.yaml"]) == 6


def test_revision_1_is_graded_on_the_key_as_it_reads_at_revision_1(corpus: Corpus) -> None:
    review = _review(corpus, 1)
    by_id = {d["id"]: d for d in review.key["defects.yaml"]}
    assert sorted(by_id) == ["D-TP201OQ-002", "D-TP201OQ-005", "D-TP201OQ-014"]
    # The anchors are revision 1's: OQ-03 keeps its defect with another limit.
    (loc,) = by_id["D-TP201OQ-002"]["locations"]
    assert (loc["rev"], loc["text"]) == (1, "minimal 110.000 tablet/jam")
    assert len(review.key["test_steps.yaml"]) == 28
    assert len(review.key["clean_traps.yaml"]) == 6


def test_0_1_0_key_reads_the_same_at_revision_0(corpus: Corpus) -> None:
    package = load_package(WORLD_0_1_0)
    key = load_package_key(package_key_dir(ROOT / "answer_key", package.id, package.version))
    review = ReviewPackage.of(package, render_draft(package, corpus.eq), key)
    assert review.key == key
    assert len(review.key["defects.yaml"]) == 8


@pytest.mark.parametrize(("rev", "defects"), [(0, 13), (1, 3)])
def test_the_oracle_scores_full_marks_at_each_revision(
    corpus: Corpus, rev: int, defects: int
) -> None:
    review = _review(corpus, rev)
    key = load_key(TP201_KEY)
    best = perfect_review(key, review)
    report = score(best, key, PageTexts(corpus, extra=[review.draft]), package=review)
    rp = report["review_package"]
    assert report["gates"]["passed"]
    assert rp["counts"]["recall"] == {"k": defects, "n": defects, "rate": 1.0}
    assert rp["metrics"]["wrong_findings"] == 0
    assert rp["counts"]["clean_traps_without_finding"]["rate"] == 1.0


def test_the_cli_grades_the_chosen_revision(
    corpus: Corpus, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "build_corpus", lambda eq: corpus)
    out = tmp_path / "r"
    for rev, defects in ((0, 13), (1, 3)):
        review = _review(corpus, rev)
        sub = tmp_path / f"rev{rev}.json"
        sub.write_text(
            perfect_review(load_key(TP201_KEY), review).model_dump_json(exclude_none=True),
            encoding="utf-8",
        )
        argv = [str(TP201), str(sub), "--key", str(ROOT / "answer_key"), "--out", str(out)]
        argv += ["--package", str(WORLD), "--draft-rev", str(rev)]
        assert cli.main(argv) == 0
        report = json.loads((out / "report.json").read_text(encoding="utf-8"))
        assert report["review_package"]["counts"]["recall"]["n"] == defects
        assert report["review_package"]["draft_rev"] == rev


def test_a_revision_the_package_does_not_have_is_refused(
    corpus: Corpus, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "build_corpus", lambda eq: corpus)
    sub = tmp_path / "s.json"
    sub.write_text(
        perfect_review(load_key(TP201_KEY), _review(corpus, 0)).model_dump_json(exclude_none=True),
        encoding="utf-8",
    )
    argv = [str(TP201), str(sub), "--key", str(ROOT / "answer_key"), "--out", str(tmp_path / "r")]
    assert cli.main([*argv, "--package", str(WORLD), "--draft-rev", "7"]) == 2
