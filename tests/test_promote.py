"""``traceq_eval promote`` (#86): a live run folder into the recordings layout and a baseline.

The live run is rebuilt from the committed top-up run r10 of TP-201 (its live ``run.json``,
and the submission the replay of its recordings gives, with the live run id), so the
expected files are the ones ``promote`` committed for r10: the report, the run metadata, the
baseline and the README column. No live call is made. (Until r9 it used r7 of TP-202,
whose ``extract`` answers no longer replay on the current prompt.)
"""

from __future__ import annotations

import json
import shutil
from importlib.metadata import version
from pathlib import Path
from typing import Any

import pytest

from traceq.runs.run import run
from traceq_eval import promote
from traceq_eval.__main__ import main

ROOT = Path(__file__).resolve().parents[1]
R10 = ROOT / "recordings" / "haiku-r10"
MANIFEST = ROOT / "recordings" / "corpus-0.1.1"
WORLD = ROOT / "world" / "tp201.yaml"
KEY = ROOT / "answer_key"
# The dev Equipment: the test reads report items and recorded requests, which the
# held-out Equipment's must not be.
TAG = "TP-201"
# The baseline r10 gave; a later baseline change moves it to a fixture, as r7's was.
R10_BASELINE = ROOT / "baselines" / f"{TAG}.json"

README_COLUMN = """\
| | TP-201 (dev) |
|---|---|
| run id | 20261117T211439Z-f6ddbf |
| coverage | 30/38 |
| value | 29/38 |
| defect recall | 5/7 |
| probes fabricated | 0/6 |
| fabrication | 0/183 |
| gates | PASS |
| calls (live) | 149 (1) |
| tokens in/out | 523136/51461 |
| cost USD (live) | 0.039022 (0.001398) |"""


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _stamped(path: Path) -> Any:
    """A committed file as ``promote`` writes it today: ``promote`` stamps the installed
    dataset version, which may be newer than the run's; every other field must match."""
    data = _json(path)
    data["dataset"]["version"] = version("traceq-dataset")
    return data


def _dump(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


@pytest.fixture(scope="module")
def live_run(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A live run folder as ``traceq run --live`` leaves it: r10's TP-201 run, a top-up."""
    tmp = tmp_path_factory.mktemp("live")
    out = run(MANIFEST, tmp, R10, "claude-haiku-5-5", equipment=TAG)
    metadata = _json(R10 / f"run-{TAG}.json")
    sub = _json(out.folder / "submission.json")
    sub["system"]["run_id"] = metadata["run_id"]
    folder = tmp / metadata["run_id"]
    out.folder.rename(folder)
    _dump(folder / "submission.json", sub)
    shutil.copyfile(R10 / f"run-{TAG}.json", folder / "run.json")
    return folder


@pytest.fixture
def recordings(tmp_path: Path) -> Path:
    """A copy of r10 without its report and run metadata, as before the promotion."""
    target = tmp_path / "recordings" / "haiku-r11"
    shutil.copytree(R10, target, ignore=shutil.ignore_patterns("report-*", "run-*"))
    return target


def test_promote_writes_the_recordings_layout_and_the_baseline(
    live_run: Path, recordings: Path, tmp_path: Path
) -> None:
    baseline = tmp_path / "baselines" / f"{TAG}.json"
    got = promote.promote(
        live_run, recordings, corpus=MANIFEST, world=WORLD, key=KEY, baseline=baseline
    )

    assert _json(recordings / f"report-{TAG}.json") == _stamped(R10 / f"report-{TAG}.json")
    assert (recordings / f"run-{TAG}.json").read_bytes() == (R10 / f"run-{TAG}.json").read_bytes()
    assert _json(baseline) == _stamped(R10_BASELINE)
    assert got.baseline == baseline
    assert got.column == README_COLUMN


def test_a_failed_gate_writes_the_recordings_but_no_baseline(
    live_run: Path, recordings: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # A key that expects `partial` where the run claims `covered_by_vendor` trips the gate.
    key = tmp_path / "key"
    shutil.copytree(KEY / TAG, key / TAG)
    report = _json(R10 / f"report-{TAG}.json")
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
    # A call this run makes (its `transport` votes are TP-201's only), not the first file
    # the glob lists: that order differs by OS and may be another Equipment's call.
    voted = [
        p
        for p in sorted(recordings.glob("*.json"))
        if _json(p).get("prompt") == "transport" and "TP201" in _json(p)["request"]["user"]
    ]
    assert voted
    voted[0].unlink()

    with pytest.raises(promote.PromoteError, match="does not hold every call"):
        promote.promote(live_run, recordings, corpus=MANIFEST, world=WORLD, key=KEY)
    assert not list(recordings.glob("report-*"))
