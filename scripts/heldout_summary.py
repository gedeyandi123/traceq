"""Fail-closed summary of a scorer ``report.json``, for held-out results (#235).

    uv run python -I scripts/heldout_summary.py <report.json> [--aggregate]

A report carries document text (quotes, requirement text, OCR readings), so a held-out
report is never read whole. This prints its gates, every k/n figure and, for a failing
gate, the item ids with their expected and got classes. It fails closed by type, not by
blocklist: every string it prints is

- a field name from the fixed allowlists below,
- an item id matching ``ID`` (one to five capitals, then one to three hyphenated groups of
  one to eight capitals or digits: ``URS-TP201-001``, ``SAT-TP201``, ``TS-URS-TP201-001``),
- a class from the scorer's or the dataset's enums (imported, never copied), or
- a gate name from the scorer's ``GATES``.

Any other string prints as ``<redacted n chars>``; numbers print as numbers; any other
value (a list, an object, a string where a number belongs) prints as ``<redacted>`` and is
never descended into. Unknown top-level keys are only counted. Item fields that hold text
by design (``where``, ``quote``) are always redacted.

``--aggregate`` prints only the gates and the k/n figures, no item ids.

Exit code 0 when the summary is printed, 2 when the report cannot be read; the error names
only the exception type, never its message (which could quote the file).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import cast, get_args

from traceq_dataset.review_package import DEFECT_TYPES
from traceq_dataset.schema import CoverageClass
from traceq_eval.citations import Status
from traceq_eval.headline import HEADLINE
from traceq_eval.report import PACKAGE_COUNTS
from traceq_eval.score import GATES, NO_CITATION, Split

ID = re.compile(r"[A-Z]{1,5}(-[A-Z0-9]{1,8}){1,3}")
"""An item id (requirement, document, step). Matched in full, so no text can ride along."""

SPLITS: frozenset[str] = frozenset(get_args(Split))
TOP_LEVEL = frozenset(
    (
        "dataset",
        "submission",
        "scorer_version",
        "equipment",
        "split",
        "headline",
        "gates",
        "fabrication",
        "citations",
        "requirements",
        "defects",
        "ambiguous",
        "probes",
        "documents",
        "test_steps",
        "ocr",
        "review_package",
        "not_scored",
        "ratchet",
    )
)
"""Every top-level key the scorer writes, either report shape (Equipment or package)."""

STATUSES: frozenset[str] = frozenset((*map(str, Status), NO_CITATION))
CLASS_FIELDS: dict[str, frozenset[str]] = {
    "expected": frozenset(map(str, CoverageClass)),
    "got": frozenset(map(str, CoverageClass)),
    "status": STATUSES,
}
ID_FIELDS = ("requirement", "step", "draft_step", "doc")
NUMBER_FIELDS = ("rev", "page", "ratio")
ITEM_FIELDS = (
    *("step", "draft_step", "requirement", "where", "doc", "rev", "page", "quote"),
    *("status", "ratio", "expected", "got"),
)
"""Gate item fields, in print order. Any other field is shown only as a redacted name."""
PACKAGE_FIGURES = frozenset((*PACKAGE_COUNTS, *(f"recall_by_type.{t}" for t in DEFECT_TYPES)))


def redacted(value: object) -> str:
    return f"<redacted {len(value)} chars>" if isinstance(value, str) else "<redacted>"


def as_dict(value: object) -> dict[str, object]:
    return cast(dict[str, object], value) if isinstance(value, dict) else {}


def as_list(value: object) -> list[object]:
    return cast(list[object], value) if isinstance(value, list) else []


def number(value: object) -> str:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return redacted(value)
    return str(value)


def member(value: object, allowed: frozenset[str] | tuple[str, ...]) -> str:
    return value if isinstance(value, str) and value in allowed else redacted(value)


def item_id(value: object) -> str:
    return value if isinstance(value, str) and ID.fullmatch(value) else redacted(value)


def k_of_n(figure: object) -> str:
    f = as_dict(figure)
    return f"{number(f.get('k'))}/{number(f.get('n'))}"


def item(entry: object) -> str:
    fields = as_dict(entry)
    if not isinstance(entry, dict):
        return redacted(entry)
    out: list[str] = []
    for name in ITEM_FIELDS:
        if name not in fields:
            continue
        value = fields[name]
        if name in ID_FIELDS:
            shown = item_id(value)
        elif name in NUMBER_FIELDS:
            shown = number(value)
        elif name in CLASS_FIELDS:
            shown = member(value, CLASS_FIELDS[name])
        else:
            shown = redacted(value)
        out.append(f"{name} {shown}")
    out += [f"{redacted(k)} <redacted>" for k in fields if k not in ITEM_FIELDS]
    return " ".join(out)


def gates(report: dict[str, object], aggregate: bool) -> list[str]:
    raw = as_dict(report.get("gates"))
    passed = raw.get("passed")
    out = [f"gates {'PASS' if passed is True else 'FAIL'}"]
    for name, value in raw.items():
        if name == "passed":
            continue
        g = as_dict(value)
        ok = g.get("passed") is True
        out.append(
            f"gate {member(name, GATES)} {'pass' if ok else 'FAIL'} count {number(g.get('count'))}"
        )
        if ok or aggregate or name not in GATES:
            continue
        out += [f"  - {item(i)}" for i in as_list(g.get("items"))]
        if not isinstance(g.get("items"), list):
            out.append(f"  items {redacted(g.get('items'))}")
    return out


def figures(report: dict[str, object]) -> list[str]:
    out = [
        f"{member(name, HEADLINE)} {k_of_n(f)}"
        for name, f in as_dict(report.get("headline")).items()
    ]
    fab = as_dict(report.get("fabrication"))
    out.append(f"fabrication {number(fab.get('fabricated'))}/{number(fab.get('claims'))}")
    package = as_dict(as_dict(report.get("review_package")).get("counts"))
    out += [
        f"review_package {member(name, PACKAGE_FIGURES)} {k_of_n(f)}" for name, f in package.items()
    ]
    return out


def counts(report: dict[str, object]) -> list[str]:
    cit = as_dict(report.get("citations"))
    by_status = as_dict(cit.get("by_status"))
    return [
        f"citations total {number(cit.get('total'))}",
        *(f"citations {member(s, STATUSES)} {number(n)}" for s, n in by_status.items()),
    ]


def summary(report: object, aggregate: bool) -> list[str]:
    r = as_dict(report)
    if not isinstance(report, dict):
        return [f"report {redacted(report)}"]
    out: list[str] = []
    if not aggregate:
        out += [
            f"equipment {item_id(r.get('equipment'))}",
            f"split {member(r.get('split'), SPLITS)}",
        ]
    out += gates(r, aggregate) + figures(r)
    if not aggregate:
        out += counts(r)
    unknown = sum(k not in TOP_LEVEL for k in r)
    if unknown:
        out.append(f"<unknown key redacted> {unknown}")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fail-closed summary of a scorer report.json.")
    parser.add_argument("report", type=Path)
    parser.add_argument("--aggregate", action="store_true", help="gates and k/n only, no ids")
    args = parser.parse_args(argv)
    try:
        report: object = json.loads(Path(args.report).read_text(encoding="utf-8"))
        lines = summary(report, args.aggregate)
    except Exception as e:  # the message could quote the file: name only the type
        print(f"cannot summarise the report: {type(e).__name__}", file=sys.stderr)
        return 2
    sys.stdout.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
