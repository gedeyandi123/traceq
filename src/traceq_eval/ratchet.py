"""Ratchet against the accepted baseline (design section 9, "Gates" and "Running").

The gates hold a floor of 0; every other metric may not get worse than the accepted
baseline. A baseline is one small JSON file per Equipment, ``baselines/<Equipment>.json``,
written from a report by ``--write-baseline`` and accepted through a PR that links the eval
run. It records what the run was scored against (dataset version, T0, seed, the answer
key's SHA-256, scorer version), the system that produced it (name, model, prompt, run id)
and the value of every ratcheted metric. A Review Package has its own baseline,
``baselines/<package id>.json``, which also records the package and its answer key's SHA-256;
a package report is compared with that baseline only (``RATCHETED_REVIEW_PACKAGE``).

Comparison rules:

- **Direction** per metric (``RATCHETED``): rates of things found go up, rates and counts of
  things made up or got wrong go down (OCR character error rate included). Sizes, counts
  that only describe the submission, and severity agreement (severity awaits the
  practitioner) are reported, not ratcheted.
- **Tolerance 0.** The CI gate replays recorded outputs and the scorer is deterministic, so
  any change is a real one; a trade-off (recall up, precision down) is accepted by a PR
  that updates the baseline, not by a margin.
- **No value** (``None``, ``"not_scored"``, or missing): none in both is ``n/a``; a value only
  now is ``new`` (passes, a new baseline may take it in); a value only in the baseline is
  ``lost`` (fails: the run no longer produces what the baseline measured).
- **Not comparable** (fails, no per-metric verdicts): a different answer key SHA-256, T0,
  seed, or dataset MAJOR/MINOR version. Such a change needs a full live eval and a new
  baseline (Q41). A different dataset PATCH or scorer version is a warning only: the
  comparison is what shows the effect of a scorer change.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterator, Mapping
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from traceq_eval.submission import System

BASELINE_VERSION = 1
EPS = 1e-9


class Direction(StrEnum):
    UP = "higher"
    DOWN = "lower"


UP, DOWN = Direction.UP, Direction.DOWN

RATCHETED: tuple[tuple[str, Direction], ...] = (
    ("fabrication.rate", DOWN),
    ("citations.verified_rate", UP),
    ("citations.by_status.value_not_in_quote", DOWN),
    ("citations.by_status.too_long", DOWN),
    ("requirements.coverage_accuracy", UP),
    ("requirements.coverage_macro_f1", UP),
    ("requirements.value_accuracy", UP),
    ("requirements.superseded_values", DOWN),
    ("requirements.source_citation_rate", UP),
    ("requirements.evidence_precision", UP),
    ("requirements.evidence_recall", UP),
    ("requirements.unknown_requirements", DOWN),
    ("requirements.segmentation_recall", UP),
    ("requirements.segmentation_precision", UP),
    ("defects.recall", UP),
    ("defects.precision", UP),
    ("defects.f1", UP),
    ("defects.recall_by_layer.*", UP),
    ("defects.recall_by_severity.*", UP),
    ("defects.mislabelled", DOWN),
    ("defects.false_positives", DOWN),
    ("defects.false_positives_on_clean_documents", DOWN),
    ("ambiguous.asked_rate", UP),
    ("ambiguous.silently_resolved", DOWN),
    ("probes.fabrication_rate", DOWN),
    ("probes.fabrication_rate_by_kind.*", DOWN),
    ("documents.precision", UP),
    ("documents.recall", UP),
    ("documents.f1", UP),
    ("documents.flagged_but_in_corpus", DOWN),
    ("test_steps.site_test_recall", UP),
    ("test_steps.criteria_pass_rate.*", UP),
    ("ocr.entry_recall", UP),
    ("ocr.localisation_rate", UP),
    ("ocr.exact_match_rate", UP),
    ("ocr.cer", DOWN),
    ("ocr.cer_by_kind.*", DOWN),
    ("ocr.cer_by_level.*", DOWN),
)
"""Ratcheted metrics. ``section.name`` reads ``report[section]["metrics"][name]`` (or
``report[section][name]`` for ``fabrication`` and ``citations``); ``.*`` expands a dict
metric to one entry per key; a list counts its items."""

RATCHETED_REVIEW_PACKAGE: tuple[tuple[str, Direction], ...] = (
    ("fabrication.rate", DOWN),
    ("citations.verified_rate", UP),
    ("citations.by_status.value_not_in_quote", DOWN),
    ("citations.by_status.too_long", DOWN),
    ("review_package.ac_reading_rate", UP),
    ("review_package.recall", UP),
    ("review_package.recall_by_type.*", UP),
    ("review_package.precision", UP),
    ("review_package.wrong_findings", DOWN),
    ("review_package.clean_trap_rate", UP),
    ("review_package.injection_probe_pass_rate", UP),
)
"""Ratcheted metrics of a Review Package report, against the package's own baseline
(``baselines/<package id>.json``, spec #196). The not-compared count is reported, not
ratcheted: fewer is not better while a row that is not compared is the honest answer."""


def ratcheted(report: Mapping[str, Any]) -> tuple[tuple[str, Direction], ...]:
    return RATCHETED_REVIEW_PACKAGE if "review_package" in report else RATCHETED


class BaselineError(ValueError):
    """The baseline file is malformed or for another Equipment."""


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DatasetRef(_Model):
    version: str
    t0: str
    seed: int
    answer_key_sha256: str


class PackageRef(_Model):
    """The Review Package a baseline was scored against."""

    id: str
    version: str
    answer_key_sha256: str


class Baseline(_Model):
    version: Literal[1] = BASELINE_VERSION
    equipment: str
    review_package: PackageRef | None = None
    dataset: DatasetRef
    scorer_version: str
    submission: System
    metrics: dict[str, float | None]


# --- Metrics ------------------------------------------------------------------------------


def _number(v: Any) -> float | None:
    if isinstance(v, bool) or v is None or isinstance(v, str):
        return None  # "not_scored"
    if isinstance(v, list):
        return float(len(v))
    return float(v)


def metrics(report: Mapping[str, Any]) -> dict[str, float | None]:
    """The ratcheted metrics of a report, flat: ``{"defects.recall_by_layer.paper": 0.5}``."""
    out: dict[str, float | None] = {}
    for path, _ in ratcheted(report):
        section, *rest = path.split(".")
        node: Any = report[section].get("metrics", report[section])
        for part in rest[:-1]:
            node = node.get(part, {})
        if rest[-1] == "*":
            for k, v in sorted(node.items()):
                out[f"{path[:-2]}.{k}"] = _number(v)
        else:
            out[path] = _number(node.get(rest[-1]))
    return out


def _spec(
    name: str, table: tuple[tuple[str, Direction], ...] = RATCHETED
) -> tuple[int, Direction] | None:
    """Position in ``table`` (the report order) and direction of a flat metric name."""
    for i, (path, d) in enumerate(table):
        if name == path or (path.endswith(".*") and name.startswith(path[:-1])):
            return i, d
    return None


# --- Baseline file ------------------------------------------------------------------------


def from_report(report: Mapping[str, Any]) -> Baseline:
    """A baseline from a scored report with metadata. A run that fails a gate is no baseline."""
    if not report["gates"]["passed"]:
        raise BaselineError("a run that fails a gate cannot be a baseline")
    package = report["dataset"].get("review_package")
    return Baseline(
        equipment=report["equipment"],
        review_package=None if package is None else PackageRef.model_validate(package),
        dataset=DatasetRef.model_validate(
            {k: report["dataset"][k] for k in DatasetRef.model_fields}
        ),
        scorer_version=report["scorer_version"],
        submission=System.model_validate(report["submission"]),
        metrics=metrics(report),
    )


def dump(baseline: Baseline, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(baseline.model_dump(mode="json", exclude_none=True), indent=2)
    path.write_text(text + "\n", encoding="utf-8", newline="\n")


def read(path: Path) -> Baseline:
    try:
        return Baseline.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise BaselineError(f"invalid baseline {path}: {e}") from e


# --- Comparison ---------------------------------------------------------------------------


def _major_minor(v: str) -> tuple[str, ...]:
    return tuple(v.split(".")[:2])


def _incomparable(b: Baseline, report: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    ds = report["dataset"]
    reasons, warnings = [], []
    for k in ("answer_key_sha256", "t0", "seed"):
        if str(getattr(b.dataset, k)) != str(ds[k]):
            reasons.append(f"{k} differs: baseline {getattr(b.dataset, k)}, run {ds[k]}")
    if _major_minor(b.dataset.version) != _major_minor(ds["version"]):
        reasons.append(
            f"dataset version differs: baseline {b.dataset.version}, run {ds['version']} "
            "(MAJOR/MINOR: a full live eval and a new baseline are needed)"
        )
    elif b.dataset.version != ds["version"]:
        warnings.append(f"dataset PATCH differs: baseline {b.dataset.version}, run {ds['version']}")
    package = ds.get("review_package")
    if b.review_package is not None and package is not None:
        bp = b.review_package
        if bp.answer_key_sha256 != package["answer_key_sha256"]:
            reasons.append(
                f"Review Package answer key differs: baseline {bp.answer_key_sha256}, "
                f"run {package['answer_key_sha256']}"
            )
        if _major_minor(bp.version) != _major_minor(package["version"]):
            reasons.append(
                f"Review Package version differs: baseline {bp.version}, run {package['version']}"
            )
        elif bp.version != package["version"]:
            warnings.append(
                f"Review Package PATCH differs: baseline {bp.version}, run {package['version']}"
            )
    if b.scorer_version != report["scorer_version"]:
        warnings.append(
            f"scorer version differs: baseline {b.scorer_version}, run {report['scorer_version']}"
        )
    return reasons, warnings


def _rows(
    base: Mapping[str, float | None],
    now: Mapping[str, float | None],
    table: tuple[tuple[str, Direction], ...],
) -> Iterator[dict]:
    specs = {n: s for n in set(base) | set(now) if (s := _spec(n, table))}
    for name in sorted(specs, key=lambda n: (specs[n][0], n)):
        b, c, d = base.get(name), now.get(name), specs[name][1]
        delta = None if b is None or c is None else round(c - b, 6)
        if b is None:
            status = "n/a" if c is None else "new"
        elif c is None:
            status = "lost"
        elif math.isclose(b, c, abs_tol=EPS):
            status = "same"
        elif (c > b) == (d is UP):
            status = "improved"
        else:
            status = "regressed"
        yield {
            "metric": name,
            "direction": str(d),
            "baseline": b,
            "run": c,
            "delta": delta,
            "status": status,
        }


FAILING = frozenset({"regressed", "lost"})


def compare(baseline: Baseline, report: Mapping[str, Any]) -> dict[str, Any]:
    """The ratchet verdict of a scored report (with metadata) against a baseline."""
    if baseline.equipment != report["equipment"]:
        raise BaselineError(
            f"baseline is for {baseline.equipment}, the report for {report['equipment']}"
        )
    package = report.get("review_package")
    ours = None if package is None else package["id"]
    theirs = None if baseline.review_package is None else baseline.review_package.id
    if ours != theirs:
        raise BaselineError(f"baseline is for Review Package {theirs}, the report for {ours}")
    reasons, warnings = _incomparable(baseline, report)
    table = ratcheted(report)
    dropped = sorted(n for n in baseline.metrics if _spec(n, table) is None)
    if dropped:
        warnings.append(f"no longer ratcheted, ignored: {', '.join(dropped)}")
    rows = [] if reasons else list(_rows(baseline.metrics, metrics(report), table))
    failing = [r["metric"] for r in rows if r["status"] in FAILING]
    return {
        "passed": not reasons and not failing,
        "comparable": not reasons,
        "baseline": {
            "dataset": baseline.dataset.model_dump(),
            "scorer_version": baseline.scorer_version,
            "submission": baseline.submission.model_dump(exclude_none=True),
        },
        "reasons": reasons,
        "warnings": warnings,
        "failing": failing,
        "metrics": rows,
    }
