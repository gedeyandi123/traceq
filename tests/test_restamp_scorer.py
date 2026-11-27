"""Scorer 0.9.0 (ticket #393) and ``scripts/restamp_scorer.py``, which re-stamps a committed
report and its baseline from a zero-call replay only when nothing but ``scorer_version`` moves.

Only fake reports and the committed dev (TP-201) files are read here, never a held-out file.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from traceq_eval import ratchet
from traceq_eval.score import SCORER_VERSION

ROOT = Path(__file__).resolve().parents[1]
RECORDINGS = ROOT / "recordings"
BASELINES = ROOT / "baselines"

DEV_BASELINES = {
    "TP-201.json": "haiku-r10/report-TP-201.json",
    "TP-201-OQ-draft.json": "haiku-oq-draft-r8/report-TP-201-OQ-draft.json",
    "TP-201-OQ-draft-0.1.0.json": "haiku-oq-draft-r3/report-TP-201-OQ-draft.json",
}
"""Every dev baseline and the committed report it was written from."""

KEPT_AT_0_8_0 = {"haiku-oq-draft-r3/report-TP-201-OQ-draft.json"}
"""r3's report stays the record of that run at scorer 0.8.0 (owner decision, #393): scored now,
the unit table compares OQ-24 and OQ-27 (19 Test Steps not compared become 17) and the capability
finding on OQ-04 is ``not_graded``, so the report is not the replay's. Its baseline's ratcheted
metrics re-score the same, so the 0.1.0 baseline carries 0.9.0."""


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "restamp_scorer", ROOT / "scripts" / "restamp_scorer.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses look their module up while it loads
    spec.loader.exec_module(module)
    return module


restamp = _load_script()


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def test_the_scorer_is_0_9_0() -> None:
    assert SCORER_VERSION == "0.9.0"


@pytest.mark.parametrize(("baseline", "report"), sorted(DEV_BASELINES.items()))
def test_every_dev_baseline_and_its_report_carry_scorer_0_9_0(baseline: str, report: str) -> None:
    assert ratchet.read(BASELINES / baseline).scorer_version == "0.9.0"
    expected = "0.8.0" if report in KEPT_AT_0_8_0 else "0.9.0"
    assert _json(RECORDINGS / report)["scorer_version"] == expected


def test_revision_1_of_r8_carries_scorer_0_9_0() -> None:
    report = _json(RECORDINGS / "haiku-oq-draft-r8" / "report-TP-201-OQ-draft-rev1.json")
    assert report["scorer_version"] == "0.9.0"


# --- scripts/restamp_scorer.py, on fake files ---------------------------------------------


def _report(version: str = "0.8.0") -> dict[str, Any]:
    """The committed TP-201 report (dev) as a stand-in, at ``version``."""
    report = _json(RECORDINGS / "haiku-r10" / "report-TP-201.json")
    return {**report, "scorer_version": version}


def _files(tmp_path: Path, report: dict[str, Any]) -> tuple[Path, Path]:
    """The report as ``promote`` writes it and its baseline as ``ratchet.dump`` writes it."""
    report_path, baseline_path = tmp_path / "report.json", tmp_path / "baseline.json"
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    report_path.write_text(text, encoding="utf-8", newline="\n")
    ratchet.dump(ratchet.from_report(report), baseline_path)
    return report_path, baseline_path


def _bytes(*paths: Path) -> list[bytes]:
    return [p.read_bytes() for p in paths]


def _changed_lines(before: bytes, after: bytes) -> list[tuple[str, str]]:
    old, new = before.decode().splitlines(), after.decode().splitlines()
    assert len(old) == len(new)
    return [(a, b) for a, b in zip(old, new, strict=True) if a != b]


def test_an_equal_replay_re_stamps_only_the_scorer_version_line(tmp_path: Path) -> None:
    report_path, baseline_path = _files(tmp_path, _report())
    before = _bytes(report_path, baseline_path)

    code = restamp.apply(_report("0.9.0"), report_path, baseline_path, version="0.9.0")

    assert code == restamp.EQUAL
    after = _bytes(report_path, baseline_path)
    line = ('  "scorer_version": "0.8.0",', '  "scorer_version": "0.9.0",')
    assert _changed_lines(before[0], after[0]) == [line]
    assert _changed_lines(before[1], after[1]) == [line]


def test_a_report_without_baseline_is_re_stamped_alone(tmp_path: Path) -> None:
    report_path, _ = _files(tmp_path, _report())

    assert restamp.apply(_report("0.9.0"), report_path, None, version="0.9.0") == restamp.EQUAL
    assert _json(report_path) == _report("0.9.0")


@pytest.mark.parametrize(
    "change",
    [
        lambda r: r["fabrication"].update(fabricated=1),
        lambda r: r["citations"]["by_status"].update(too_long=1),
        lambda r: r.update(extra_section={}),
        lambda r: r.pop("headline"),
        lambda r: r["submission"].update(run_id="another"),
    ],
)
def test_any_other_difference_writes_nothing(tmp_path: Path, change: Any) -> None:
    report_path, baseline_path = _files(tmp_path, _report())
    before = _bytes(report_path, baseline_path)
    fresh = _report("0.9.0")
    change(fresh)

    code = restamp.apply(fresh, report_path, baseline_path, version="0.9.0")

    assert code == restamp.DIFFERENT
    assert _bytes(report_path, baseline_path) == before


def test_a_baseline_that_is_not_the_reports_writes_nothing(tmp_path: Path) -> None:
    report_path, baseline_path = _files(tmp_path, _report())
    other = copy.deepcopy(_report())
    other["fabrication"]["rate"] = 0.5
    ratchet.dump(ratchet.from_report(other), baseline_path)
    before = _bytes(report_path, baseline_path)

    code = restamp.apply(_report("0.9.0"), report_path, baseline_path, version="0.9.0")

    assert code == restamp.DIFFERENT
    assert _bytes(report_path, baseline_path) == before


def test_a_kept_report_re_stamps_only_its_baseline(tmp_path: Path) -> None:
    """A report kept as the record of its run may differ from the replay; its baseline is
    re-stamped when the replay gives the same baseline."""
    report_path, baseline_path = _files(tmp_path, _report())
    before = _bytes(report_path, baseline_path)
    fresh = _report("0.9.0")
    fresh["citations"]["total"] += 2  # not a ratcheted metric

    code = restamp.apply(fresh, report_path, baseline_path, version="0.9.0", keep_report=True)

    assert code == restamp.EQUAL
    after = _bytes(report_path, baseline_path)
    assert after[0] == before[0]
    line = ('  "scorer_version": "0.8.0",', '  "scorer_version": "0.9.0",')
    assert _changed_lines(before[1], after[1]) == [line]


def test_a_kept_report_whose_baseline_moves_writes_nothing(tmp_path: Path) -> None:
    report_path, baseline_path = _files(tmp_path, _report())
    before = _bytes(report_path, baseline_path)
    fresh = _report("0.9.0")
    fresh["fabrication"]["rate"] = 0.5

    code = restamp.apply(fresh, report_path, baseline_path, version="0.9.0", keep_report=True)

    assert code == restamp.DIFFERENT
    assert _bytes(report_path, baseline_path) == before


def test_check_only_compares(tmp_path: Path) -> None:
    report_path, baseline_path = _files(tmp_path, _report())
    before = _bytes(report_path, baseline_path)

    code = restamp.apply(_report("0.9.0"), report_path, baseline_path, version="0.9.0", write=False)

    assert code == restamp.EQUAL
    assert _bytes(report_path, baseline_path) == before


def test_the_messages_name_only_the_check(tmp_path: Path, capsys: Any) -> None:
    """A held-out run prints only fixed messages: never a key, value or diff."""
    marker = "MARKER-7f3a9c"
    report_path, baseline_path = _files(tmp_path, _report())
    fresh = _report("0.9.0")
    fresh["citations"]["by_status"][marker] = 1

    restamp.apply(fresh, report_path, baseline_path, version="0.9.0")

    out = capsys.readouterr()
    assert marker not in out.out + out.err
    assert "by_status" not in out.out + out.err
