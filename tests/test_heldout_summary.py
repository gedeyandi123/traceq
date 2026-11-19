"""``scripts/heldout_summary.py``: a fail-closed summary of a scorer report (#235).

Every string the summary prints is an allowlisted field name, a strict item id, a class
from the scorer's enums or a gate name; anything else comes out as ``<redacted n chars>``.
Only fake reports and the committed TP-201 report are used here, never a held-out file.
"""

from __future__ import annotations

import copy
import json
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from traceq_eval.score import GATES

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "heldout_summary.py"
TP201 = ROOT / "recordings" / "haiku-r10" / "report-TP-201.json"
MARKER = "zq_injected_marker"
ID = re.compile(r"\b[A-Z]{1,5}(-[A-Z0-9]{1,8}){1,3}\b")


def summarise(report: Path, *args: str) -> tuple[str, str]:
    done = subprocess.run(
        [sys.executable, "-I", str(SCRIPT), str(report), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert done.returncode == 0, done.returncode
    return done.stdout, done.stderr


def fake_report() -> dict[str, Any]:
    """A failing report in the scorer's shape, with document text where the scorer puts it."""
    return {
        "dataset": {"version": "0.1.1", "equipment": "TP-201"},
        "submission": {"name": "traceq", "prompt": MARKER},
        "scorer_version": "0.8.0",
        "equipment": "TP-201",
        "split": "dev",
        "headline": {
            "defects.recall": {"k": 5, "n": 7, "rate": 0.7143, "better": "higher"},
            "fabrication.rate": {"k": 1, "n": 180, "rate": 0.0056, "better": "lower"},
        },
        "gates": {
            "passed": False,
            "fabricated_acceptance_criterion": {
                "count": 1,
                "floor": 0,
                "passed": False,
                "items": [
                    {
                        "step": "TS-URS-TP201-004",
                        "requirement": "URS-TP201-004",
                        "status": "no_citation",
                    }
                ],
            },
            "fabricated_citation": {
                "count": 1,
                "floor": 0,
                "passed": False,
                "items": [
                    {
                        "where": f"step TS-URS-TP201-004 acceptance {MARKER}",
                        "doc": "SAT-TP201",
                        "rev": 0,
                        "page": 3,
                        "quote": f"the pump shall {MARKER}",
                        "status": "quote_not_found",
                        "ratio": 0.41,
                    }
                ],
            },
            "fabricated_evidence": {"count": 0, "floor": 0, "passed": True, "items": []},
            "unsafe_covered_by_vendor": {
                "count": 1,
                "floor": 0,
                "passed": False,
                "items": [
                    {"requirement": "URS-TP201-001", "expected": "gap", "got": "covered_by_vendor"}
                ],
            },
        },
        "fabrication": {"claims": 180, "fabricated": 1, "rate": 0.0056},
        "citations": {
            "total": 117,
            "verified_rate": 0.9915,
            "by_status": {"verified": 116, "quote_not_found": 1},
            "failed": [{"quote": MARKER}],
        },
        "requirements": {"items": [{"id": "URS-TP201-001", "text": MARKER}]},
        "not_scored": [MARKER],
    }


def write(tmp_path: Path, report: dict[str, Any]) -> Path:
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    return path


def test_tp201_report_summarises_every_figure_without_redaction() -> None:
    report = json.loads(TP201.read_text(encoding="utf-8"))
    out, err = summarise(TP201)
    assert "redacted" not in out + err
    for name, figure in report["headline"].items():
        assert f"{name} {figure['k']}/{figure['n']}" in out
    for name in GATES:
        assert f"gate {name} pass count 0" in out
    assert "gates PASS" in out
    assert "split dev" in out


def test_gate_names_are_the_scorers() -> None:
    report = json.loads(TP201.read_text(encoding="utf-8"))
    assert tuple(k for k in report["gates"] if k != "passed") == GATES


def test_failing_gates_list_item_ids_and_classes(tmp_path: Path) -> None:
    out, err = summarise(write(tmp_path, fake_report()))
    assert "gates FAIL" in out
    assert "gate unsafe_covered_by_vendor FAIL count 1" in out
    assert "requirement URS-TP201-001 expected gap got covered_by_vendor" in out
    assert "step TS-URS-TP201-004 requirement URS-TP201-004 status no_citation" in out
    assert "doc SAT-TP201 rev 0 page 3" in out
    assert "status quote_not_found ratio 0.41" in out
    assert "fabrication 1/180" in out
    assert MARKER not in out + err


def _id_with_text(r: dict[str, Any]) -> None:
    r["gates"]["unsafe_covered_by_vendor"]["items"][0]["requirement"] = (
        f"URS-TP201-001 the pump shall {MARKER}"
    )


def _class_with_text(r: dict[str, Any]) -> None:
    r["gates"]["unsafe_covered_by_vendor"]["items"][0]["expected"] = f"gap {MARKER}"


def _gate_name_with_text(r: dict[str, Any]) -> None:
    r["gates"][f"fabricated_citation {MARKER}"] = r["gates"].pop("fabricated_citation")


def _nested_field(r: dict[str, Any]) -> None:
    r["gates"]["unsafe_covered_by_vendor"]["items"][0]["got"] = {"text": MARKER}
    r["headline"]["defects.recall"]["k"] = [MARKER]


def _unknown_item_key(r: dict[str, Any]) -> None:
    r["gates"]["unsafe_covered_by_vendor"]["items"][0][MARKER] = MARKER


def _headline_name_with_text(r: dict[str, Any]) -> None:
    r["headline"][f"defects.recall {MARKER}"] = r["headline"].pop("defects.recall")


def _very_long_string(r: dict[str, Any]) -> None:
    r["gates"]["unsafe_covered_by_vendor"]["items"][0]["requirement"] = "URS-" + "A" * 5000 + MARKER


def _status_with_text(r: dict[str, Any]) -> None:
    r["citations"]["by_status"][MARKER] = 3


@pytest.mark.parametrize(
    "inject",
    [
        _id_with_text,
        _class_with_text,
        _gate_name_with_text,
        _nested_field,
        _unknown_item_key,
        _headline_name_with_text,
        _very_long_string,
        _status_with_text,
    ],
)
def test_injected_text_is_redacted(
    tmp_path: Path, inject: Callable[[dict[str, Any]], None]
) -> None:
    report = copy.deepcopy(fake_report())
    inject(report)
    out, err = summarise(write(tmp_path, report))
    assert MARKER not in out + err
    assert re.search(r"<redacted( \d+ chars)?>", out)


def test_a_very_long_string_reports_its_length(tmp_path: Path) -> None:
    report = fake_report()
    _very_long_string(report)
    out, _ = summarise(write(tmp_path, report))
    assert f"requirement <redacted {4 + 5000 + len(MARKER)} chars>" in out


def test_unknown_top_level_keys_are_counted_not_named(tmp_path: Path) -> None:
    report = fake_report()
    report[MARKER] = MARKER
    report[MARKER + "2"] = {"x": MARKER}
    out, err = summarise(write(tmp_path, report))
    assert MARKER not in out + err
    assert "<unknown key redacted> 2" in out


def test_a_report_that_is_not_json_fails_without_echoing_it(tmp_path: Path) -> None:
    path = tmp_path / "report.json"
    path.write_text(f"{{{MARKER}", encoding="utf-8")
    done = subprocess.run(
        [sys.executable, "-I", str(SCRIPT), str(path)], capture_output=True, text=True, check=False
    )
    assert done.returncode == 2
    assert MARKER not in done.stdout + done.stderr


def test_review_package_figures_are_k_of_n(tmp_path: Path) -> None:
    report = fake_report()
    report["review_package"] = {
        "id": f"TP-201-OQ-draft {MARKER}",
        "counts": {
            "recall": {"k": 3, "n": 4, "rate": 0.75},
            "recall_by_type.requirement_not_tested": {"k": 1, "n": 2, "rate": 0.5},
            f"recall_by_type.{MARKER}": {"k": 1, "n": 1, "rate": 1.0},
        },
        "defects": [{"id": "D-TP201OQ-001", "type": MARKER}],
    }
    out, err = summarise(write(tmp_path, report), "--aggregate")
    assert "review_package recall 3/4" in out
    assert "review_package recall_by_type.requirement_not_tested 1/2" in out
    assert MARKER not in out + err


def test_aggregate_prints_gates_and_figures_without_item_ids(tmp_path: Path) -> None:
    out, err = summarise(write(tmp_path, fake_report()), "--aggregate")
    assert "gate unsafe_covered_by_vendor FAIL count 1" in out
    assert "defects.recall 5/7" in out
    assert not ID.search(out), ID.search(out)
    assert MARKER not in out + err
