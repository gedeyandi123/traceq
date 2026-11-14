"""``traceq_eval promote`` (#86): a live run folder into the recordings layout and a baseline.

The live run is rebuilt from the committed top-up run r7 of TP-202 (its live ``run.json``,
and the submission the replay of its recordings gives, with the live run id), so the
expected files are the ones committed by hand in PR #91: the report, the run metadata, the
baseline and the README column. No live call is made.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from traceq.runs.run import run
from traceq_eval import promote
from traceq_eval.__main__ import main

ROOT = Path(__file__).resolve().parents[1]
R7 = ROOT / "recordings" / "haiku-r7"
MANIFEST = ROOT / "recordings" / "corpus-0.1.0"
WORLD = ROOT / "world" / "tp202.yaml"
KEY = ROOT / "answer_key"
TAG = "TP-202"

README_COLUMN = """\
| | TP-202 (held-out) |
|---|---|
| run id | 20261114T091315Z-dcd2d1 |
| coverage | 6/13 |
| value | 10/13 |
| defect recall | 1/3 |
| probes fabricated | 0/2 |
| fabrication | 0/53 |
| gates | PASS |
| calls (live) | 68 (11) |
| tokens in/out | 131379/16068 |
| cost USD (live) | 0.010586 (0.001267) |"""


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _dump(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


@pytest.fixture(scope="module")
def live_run(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A live run folder as ``traceq run --live`` leaves it: r7's TP-202 run, a top-up."""
    tmp = tmp_path_factory.mktemp("live")
    out = run(MANIFEST, tmp, R7, "claude-haiku-5-5", equipment=TAG)
    metadata = _json(R7 / f"run-{TAG}.json")
    sub = _json(out.folder / "submission.json")
    sub["system"]["run_id"] = metadata["run_id"]
    folder = tmp / metadata["run_id"]
    out.folder.rename(folder)
    _dump(folder / "submission.json", sub)
    shutil.copyfile(R7 / f"run-{TAG}.json", folder / "run.json")
    return folder


@pytest.fixture
def recordings(tmp_path: Path) -> Path:
    """A copy of r7 without its report and run metadata, as before the promotion."""
    target = tmp_path / "recordings" / "haiku-r8"
    shutil.copytree(R7, target, ignore=shutil.ignore_patterns("report-*", "run-*"))
    return target


def test_promote_writes_the_recordings_layout_and_the_baseline(
    live_run: Path, recordings: Path, tmp_path: Path
) -> None:
    baseline = tmp_path / "baselines" / f"{TAG}.json"
    got = promote.promote(
        live_run, recordings, corpus=MANIFEST, world=WORLD, key=KEY, baseline=baseline
    )

    assert _json(recordings / f"report-{TAG}.json") == _json(R7 / f"report-{TAG}.json")
    assert (recordings / f"run-{TAG}.json").read_bytes() == (R7 / f"run-{TAG}.json").read_bytes()
    assert _json(baseline) == _json(ROOT / "baselines" / f"{TAG}.json")
    assert got.baseline == baseline
    assert got.column == README_COLUMN


def test_a_failed_gate_writes_the_recordings_but_no_baseline(
    live_run: Path, recordings: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # A key that expects `partial` where the run claims `covered_by_vendor` trips the gate.
    key = tmp_path / "key"
    shutil.copytree(KEY / TAG, key / TAG)
    report = _json(R7 / f"report-{TAG}.json")
    claimed = next(
        i["id"] for i in report["requirements"]["items"] if i["got"] == "covered_by_vendor"
    )
    reqs = key / TAG / "requirements.yaml"
    text = reqs.read_text(encoding="utf-8")
    old = "expected_coverage: covered_by_vendor"
    at = text.index(old, text.index(f"id: {claimed}"))
    reqs.write_text(text[:at] + "expected_coverage: partial" + text[at + len(old) :], "utf-8")
    baseline = tmp_path / f"{TAG}.json"
    paths = ["--corpus", str(MANIFEST), "--world", str(WORLD), "--key", str(key)]
    options = ["--recordings", str(recordings), "--baseline", str(baseline), *paths]

    code = main(["promote", str(live_run), *options])

    assert code == 1
    assert not baseline.exists()
    gates = _json(recordings / f"report-{TAG}.json")["gates"]
    assert gates["unsafe_covered_by_vendor"]["count"] == 1
    assert "| gates | FAIL (`unsafe_covered_by_vendor`: 1) |" in capsys.readouterr().out


def test_a_replay_run_is_not_promoted(live_run: Path, recordings: Path, tmp_path: Path) -> None:
    folder = tmp_path / "replay"
    shutil.copytree(live_run, folder)
    _dump(folder / "run.json", {**_json(folder / "run.json"), "mode": "replay"})

    with pytest.raises(promote.PromoteError, match="not a live one"):
        promote.promote(folder, recordings, corpus=MANIFEST, world=WORLD, key=KEY)
    assert not list(recordings.glob("report-*"))


def test_a_run_its_recordings_do_not_reproduce_is_not_promoted(
    live_run: Path, recordings: Path, tmp_path: Path
) -> None:
    folder = tmp_path / "edited"
    shutil.copytree(live_run, folder)
    sub = _json(folder / "submission.json")
    sub["requirements"][0]["coverage"] = "gap"
    _dump(folder / "submission.json", sub)

    with pytest.raises(promote.PromoteError, match="submission differs"):
        promote.promote(folder, recordings, corpus=MANIFEST, world=WORLD, key=KEY)
    assert not list(recordings.glob("report-*"))


def test_recordings_missing_a_call_are_not_promoted(live_run: Path, recordings: Path) -> None:
    # A call this run makes (its `transport` votes are TP-202's only), not the first file
    # the glob lists: that order differs by OS and may be another Equipment's call.
    voted = [
        p
        for p in sorted(recordings.glob("*.json"))
        if _json(p).get("prompt") == "transport" and "TP202" in _json(p)["request"]["user"]
    ]
    assert voted
    voted[0].unlink()

    with pytest.raises(promote.PromoteError, match="does not hold every call"):
        promote.promote(live_run, recordings, corpus=MANIFEST, world=WORLD, key=KEY)
    assert not list(recordings.glob("report-*"))
