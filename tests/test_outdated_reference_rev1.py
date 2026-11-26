"""Revision 1 of the 0.2.0 draft read live once with the rule ``outdated_reference`` on (spec
#375, ticket S2c): the two citations revision 0 got wrong are fixed (OQ-02, OQ-26) and one new
stale citation is added (OQ-12). The recordings are in ``recordings/haiku-oq-draft-r7`` beside
revision 0's; no baseline is written for revision 1 (the baseline is revision 0's). Dev only;
the type is not reviewed by a practitioner."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from traceq.runs.run import RunOutput, run
from traceq_dataset.answer_key import load_key
from traceq_dataset.corpus import Corpus
from traceq_dataset.review_package import (
    load_package,
    load_package_key,
    package_key_dir,
    render_draft,
)
from traceq_eval.citations import PageTexts
from traceq_eval.report import with_metadata
from traceq_eval.score import ReviewPackage, score
from traceq_eval.submission import Submission

ROOT = Path(__file__).resolve().parents[1]
RECORDINGS = ROOT / "recordings"
R7 = RECORDINGS / "haiku-oq-draft-r7"
TAG = "TP-201-OQ-draft"
OUTDATED = "outdated_reference"


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def replayed(tmp_path_factory: pytest.TempPathFactory) -> RunOutput:
    return run(
        RECORDINGS / "corpus-0.1.1",
        tmp_path_factory.mktemp("outdated-reference-rev1"),
        RECORDINGS / "haiku-r10",
        "claude-haiku-5-5",
        equipment="TP-201",
        review_package=RECORDINGS / "TP-201-OQ-draft-0.2.0",
        package_recordings=R7,
        draft_rev=1,
    )


@pytest.fixture(scope="module")
def report(replayed: RunOutput, tp201_corpus: Corpus) -> dict[str, Any]:
    package = load_package(ROOT / "world" / "tp201-oq-draft-0.2.0.yaml")
    key_dir = package_key_dir(ROOT / "answer_key", package.id, package.version)
    review = ReviewPackage.of(
        package, render_draft(package, tp201_corpus.eq, 1), load_package_key(key_dir)
    )
    sub = Submission.model_validate_json(
        (replayed.folder / "submission.json").read_text(encoding="utf-8")
    )
    equipment_key = ROOT / "answer_key" / "TP-201"
    scored = score(
        sub,
        load_key(equipment_key),
        PageTexts(tp201_corpus, extra=[review.draft]),
        package=review,
    )
    return with_metadata(scored, sub, tp201_corpus, equipment_key, key_dir)


def test_the_run_replays_at_tolerance_0(replayed: RunOutput, report: dict[str, Any]) -> None:
    recorded = _json(R7 / f"run-{TAG}-rev1.json")
    expected = _json(R7 / f"report-{TAG}-rev1.json")
    assert recorded["mode"] == "live" and recorded["review_package"]["calls"]["live"] == 9
    assert recorded["live_cost_usd"] == 0.004642
    assert replayed.metadata["calls"] == {"total": 158, "replayed": 158, "live": 0}
    assert replayed.metadata["cost_usd"] == recorded["cost_usd"]
    assert replayed.metadata["prompts"] == recorded["prompts"]
    assert report["gates"] == expected["gates"]
    assert report["review_package"] == expected["review_package"]


def test_the_fixed_citations_raise_nothing_and_the_new_one_is_found(
    replayed: RunOutput, report: dict[str, Any]
) -> None:
    """Dev only, n = 1 at revision 1: a smoke count. OQ-02 and OQ-26 were fixed, so no finding;
    OQ-12 cites SOP-VAL-002 Rev. 1 where the register holds Rev. 2."""
    draft = _json(replayed.folder / "protocol_draft.json")
    found = [(f["test_step"], f["label"]) for f in draft["findings"] if f["type"] == OUTDATED]
    assert found == [("OQ-12", "not reviewed by a practitioner")]
    rp = report["review_package"]
    assert rp["draft_rev"] == 1
    assert rp["counts"][f"recall_by_type.{OUTDATED}"] == {"k": 1, "n": 1, "rate": 1.0}
    assert rp["counts"]["recall"] == {"k": 3, "n": 3, "rate": 1.0}
    assert rp["metrics"]["wrong_findings"] == 0
    assert rp["counts"]["clean_traps_without_finding"] == {"k": 6, "n": 6, "rate": 1.0}
