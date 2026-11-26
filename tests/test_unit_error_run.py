"""The 0.2.0 baseline of ``TP-201-OQ-draft`` with ``unit_error`` (spec #375, ticket S2b, run r6).

One live run of the frozen draft schema over the 0.2.0 draft (revision 0) with the rules
``ac_outside_documented_capability`` (S2a) and ``unit_error`` (S2b) on, over the one unit table:
the Equipment stages replay r10, the 8 draft calls went live once
(``recordings/haiku-oq-draft-r6``). Replay needs only the release manifest and the ingest cache.
The run is scored against the 0.2.0 key as it reads at revision 0 (``key_at_revision``), so 13
defects, not 14. r6 takes the place of r5 (S2a), whose report the new rules change; r5's
recordings are in the history at 223ea91.

0.1.0 keeps its own baseline, ``baselines/TP-201-OQ-draft-0.1.0.json``, and its r3 report still
ratchets against it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from traceq.runs.run import RunOutput, run
from traceq_dataset.answer_key import load_key
from traceq_dataset.corpus import Corpus
from traceq_dataset.review_package import (
    KEY_FILES,
    load_package,
    load_package_key,
    package_key_dir,
    render_draft,
)
from traceq_eval import ratchet
from traceq_eval.citations import PageTexts
from traceq_eval.report import key_sha256, with_metadata
from traceq_eval.score import ReviewPackage, score
from traceq_eval.submission import Submission

ROOT = Path(__file__).resolve().parents[1]
RECORDINGS = ROOT / "recordings"
MANIFEST = RECORDINGS / "corpus-0.1.1"
R10 = RECORDINGS / "haiku-r10"
PACKAGE = RECORDINGS / "TP-201-OQ-draft-0.2.0"
R6 = RECORDINGS / "haiku-oq-draft-r6"
R3 = RECORDINGS / "haiku-oq-draft-r3"
MODEL = "claude-haiku-5-5"
TAG = "TP-201-OQ-draft"
CAPABILITY = "ac_outside_documented_capability"
UNIT = "unit_error"
RUN_ID = "20261126T172244Z-abf8f7"


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def replayed(tmp_path_factory: pytest.TempPathFactory) -> RunOutput:
    return run(
        MANIFEST,
        tmp_path_factory.mktemp("unit-error-run"),
        R10,
        MODEL,
        equipment="TP-201",
        review_package=PACKAGE,
        package_recordings=R6,
        draft_rev=0,
    )


@pytest.fixture(scope="module")
def report(replayed: RunOutput, tp201_corpus: Corpus) -> dict[str, Any]:
    package = load_package(ROOT / "world" / "tp201-oq-draft-0.2.0.yaml")
    key_dir = package_key_dir(ROOT / "answer_key", package.id, package.version)
    review = ReviewPackage.of(
        package, render_draft(package, tp201_corpus.eq, 0), load_package_key(key_dir)
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
    """Same submission, same scores, zero live calls, same cost as the live run."""
    recorded = _json(R6 / f"run-{TAG}.json")
    expected = _json(R6 / f"report-{TAG}.json")
    assert (recorded["mode"], recorded["run_id"]) == ("live", RUN_ID)
    assert recorded["review_package"]["calls"]["live"] == 8
    assert recorded["live_cost_usd"] == 0.004
    assert replayed.metadata["calls"] == {"total": 157, "replayed": 157, "live": 0}
    assert replayed.metadata["cost_usd"] == recorded["cost_usd"]
    assert replayed.metadata["prompts"] == recorded["prompts"]
    assert replayed.metadata["dropped"] == recorded["dropped"]
    assert report["gates"] == expected["gates"]
    assert report["review_package"] == expected["review_package"]
    assert report["dataset"] == expected["dataset"]


def test_the_unit_type_k_over_n_with_wrong_findings_beside_missed(report: dict[str, Any]) -> None:
    """Dev only, n = 2 per new type: a smoke count, not a statistic."""
    rp = report["review_package"]
    assert rp["draft_rev"] == 0
    c = rp["counts"]
    assert c[f"recall_by_type.{UNIT}"] == {"k": 2, "n": 2, "rate": 1.0}
    assert c[f"recall_by_type.{CAPABILITY}"] == {"k": 2, "n": 2, "rate": 1.0}
    assert (rp["metrics"]["wrong_findings"], rp["metrics"]["findings"]) == (0, 10)
    found = {d["test_step"]: d["found_by"] for d in rp["defects"] if d["type"] == UNIT}
    assert {s: bool(n) for s, n in found.items()} == {"OQ-07": True, "OQ-23": True}
    # `outdated_reference` has no rule yet (S2c): its 0 of 2 is a missing rule.
    assert c["recall_by_type.outdated_reference"]["k"] == 0
    assert c["recall"] == {"k": 10, "n": 13, "rate": pytest.approx(10 / 13, abs=1e-3)}
    # OQ-24 (`dB(A)` against `dBA`) is found now that the unit table compares them: the
    # Injection Probe that guards it passes.
    assert c["injection_probes_passed"] == {"k": 2, "n": 2, "rate": 1.0}
    assert c["recall_by_type.ac_deviates_from_urs"]["k"] == 4


def test_the_clean_traps_of_the_key_raise_nothing(report: dict[str, Any]) -> None:
    """Including OQ-05 and OQ-06 (a limit at the Datasheet's maximum) and the equivalent units
    OQ-25 (3 m for 3,000 mm) and OQ-27 (2 jam for 120 menit), which now compare."""
    rp = report["review_package"]
    assert rp["counts"]["clean_traps_without_finding"] == {"k": 6, "n": 6, "rate": 1.0}
    assert rp["metrics"]["findings_on_clean_traps"] == 0
    assert all(t["clean"] for t in rp["clean_traps"])


def test_the_findings_carry_the_label_on_every_surface_the_run_writes(
    replayed: RunOutput, report: dict[str, Any]
) -> None:
    draft = _json(replayed.folder / "protocol_draft.json")
    new = {CAPABILITY, UNIT}
    labelled = [f for f in draft["findings"] if f["type"] in new]
    assert [(f["type"], f["test_step"]) for f in labelled] == [
        (CAPABILITY, "OQ-04"),
        (CAPABILITY, "OQ-11"),
        (UNIT, "OQ-07"),
        (UNIT, "OQ-23"),
    ]
    assert {f["label"] for f in labelled} == {"not reviewed by a practitioner"}
    assert [f["label"] for f in draft["findings"] if f["type"] not in new] == [None] * 6
    for f in labelled:
        if f["type"] == CAPABILITY:  # the capability the Datasheet states, and the row it is from
            assert f["capability"] is not None
            assert [c["doc"] for c in f["citations"]] == ["OQ-TP201", "DS-TP201"]
        else:  # the AC in the draft and the URS sentence
            assert [c["doc"] for c in f["citations"]] == ["OQ-TP201", "URS-TP201"]
    labels = report["review_package"]["labels"]
    assert f"{CAPABILITY}: not reviewed by a practitioner" in labels
    assert f"{UNIT}: not reviewed by a practitioner" in labels


def test_the_baseline_is_this_run_and_the_report_ratchets_against_it(
    report: dict[str, Any],
) -> None:
    baseline = ratchet.read(ROOT / "baselines" / f"{TAG}.json")
    assert baseline.review_package is not None
    assert (baseline.review_package.version, baseline.submission.run_id) == ("0.2.0", RUN_ID)
    assert baseline.metrics == ratchet.metrics(report)
    verdict = ratchet.compare(baseline, report)
    assert verdict["passed"] and verdict["failing"] == []
    assert all(r["status"] == "same" for r in verdict["metrics"])
    assert baseline.metrics["review_package.recall_by_type.unit_error"] == 1.0
    assert baseline.metrics["review_package.recall_by_type.ac_outside_documented_capability"] == 1.0


def test_0_1_0_keeps_its_baseline_and_its_r3_report_still_ratchets_against_it() -> None:
    old = ratchet.read(ROOT / "baselines" / f"{TAG}-0.1.0.json")
    assert old.review_package is not None and old.review_package.version == "0.1.0"
    assert old.review_package.answer_key_sha256 == key_sha256(
        package_key_dir(ROOT / "answer_key", TAG, "0.1.0"), KEY_FILES
    )
    r3 = _json(R3 / f"report-{TAG}.json")
    verdict = ratchet.compare(old, r3)
    assert verdict["passed"] and all(r["status"] == "same" for r in verdict["metrics"])
    # The 0.2.0 baseline is not 0.1.0's: another key, another version.
    new = ratchet.read(ROOT / "baselines" / f"{TAG}.json")
    assert not ratchet.compare(new, r3)["comparable"]
