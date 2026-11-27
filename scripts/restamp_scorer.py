"""Re-stamp a committed scorer report and its baseline with the current scorer version (#393).

    uv run python scripts/restamp_scorer.py <target> [--check] [--explain]

The target's recorded run is replayed (every call from its recordings, none live), its
submission carries the live run's id, and it is scored by the current scorer. The fresh report
is compared with the committed one, ignoring only ``scorer_version``; the committed baseline
(if the target has one) must be the one the fresh report gives, apart from ``scorer_version``.
Only when both hold is the ``scorer_version`` line of each file re-written (``--check``:
compare, write nothing); no other byte moves. Precedent: the scorer 0.8.0 re-stamp (#204).

A held-out target (any Equipment but TP-201) runs only through
``bash scripts/heldout_run.sh <TAG> -- uv run python scripts/restamp_scorer.py <target>``.
Every message is fixed: it names the check, never a key, value or diff, and an exception's
message is dropped. ``--explain`` (dev targets only) prints the paths that differ.

Exit code 0 when the replay equals the committed report (written unless ``--check``), 3 when
anything else differs (nothing written), 2 when the replay or the scoring raised.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from traceq.runs.run import run
from traceq_dataset.answer_key import load_key
from traceq_dataset.corpus import build_corpus
from traceq_dataset.review_package import (
    load_package,
    load_package_key,
    package_key_dir,
    render_draft,
)
from traceq_dataset.world import load
from traceq_eval import ratchet
from traceq_eval.citations import PageTexts
from traceq_eval.report import with_metadata
from traceq_eval.score import SCORER_VERSION, ReviewPackage, score, split_of
from traceq_eval.submission import Submission

ROOT = Path(__file__).resolve().parents[1]

EQUAL = 0
ERROR = 2
DIFFERENT = 3

FIELD = "scorer_version"


@dataclass(frozen=True)
class Target:
    """A committed run: its replay inputs, its report and run metadata, and its baseline."""

    corpus: str
    recordings: str
    equipment: str
    report: str
    run: str
    baseline: str | None
    package: str | None = None
    """The Review Package release folder, for a package run."""
    package_world: str | None = None
    package_recordings: str | None = None
    draft_rev: int | None = None


R10 = "recordings/haiku-r10"
R8 = "recordings/haiku-oq-draft-r8"
R3 = "recordings/haiku-oq-draft-r3"
PW001 = "recordings/PW-001/haiku-r10"


def _r8(report: str, run: str, baseline: str | None, draft_rev: int) -> Target:
    """r8: the 0.2.0 Review Package run over one revision of its draft."""
    return Target(
        "recordings/corpus-0.1.1",
        R10,
        "TP-201",
        f"{R8}/{report}",
        f"{R8}/{run}",
        baseline,
        package="recordings/TP-201-OQ-draft-0.2.0",
        package_world="world/tp201-oq-draft-0.2.0.yaml",
        package_recordings=R8,
        draft_rev=draft_rev,
    )


TARGETS: dict[str, Target] = {
    "r10-TP-201": Target(
        "recordings/corpus-0.1.1",
        R10,
        "TP-201",
        f"{R10}/report-TP-201.json",
        f"{R10}/run-TP-201.json",
        "baselines/TP-201.json",
    ),
    "r10-TP-202": Target(
        "recordings/corpus-0.1.1",
        R10,
        "TP-202",
        f"{R10}/report-TP-202.json",
        f"{R10}/run-TP-202.json",
        "baselines/TP-202.json",
    ),
    "PW-001": Target(
        "recordings/corpus-0.2.0",
        PW001,
        "PW-001",
        f"{PW001}/report.json",
        f"{PW001}/run.json",
        "baselines/PW-001.json",
    ),
    "r8-rev0": _r8(
        "report-TP-201-OQ-draft.json",
        "run-TP-201-OQ-draft.json",
        "baselines/TP-201-OQ-draft.json",
        0,
    ),
    "r8-rev1": _r8("report-TP-201-OQ-draft-rev1.json", "run-TP-201-OQ-draft-rev1.json", None, 1),
    "r3": Target(
        "recordings/corpus-0.1.1",
        R10,
        "TP-201",
        f"{R3}/report-TP-201-OQ-draft.json",
        f"{R3}/run-TP-201-OQ-draft.json",
        "baselines/TP-201-OQ-draft-0.1.0.json",
        package="recordings/TP-201-OQ-draft-0.1.0",
        package_world="world/tp201-oq-draft.yaml",
        package_recordings=R3,
    ),
}


class Different(Exception):
    """The replay does not reproduce the committed run; the message is a fixed check name."""


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _world(tag: str) -> Path:
    return ROOT / "world" / f"{tag.lower().replace('-', '')}.yaml"


def replay(target: Target) -> dict[str, Any]:
    """The target's run replayed and scored now, with the live run's id and the metadata a
    baseline is written from. Raises ``Different`` when the replay is not the live run's."""
    live: dict[str, Any] = _json(ROOT / target.run)
    package = None if target.package is None else ROOT / target.package
    with tempfile.TemporaryDirectory() as tmp:
        out = run(
            ROOT / target.corpus,
            Path(tmp),
            ROOT / target.recordings,
            live["model"],
            equipment=target.equipment,
            vendor_reuse=live["settings"]["vendor_reuse"],
            review_package=package,
            package_recordings=(
                None if target.package_recordings is None else ROOT / target.package_recordings
            ),
            draft_rev=target.draft_rev,
        )
        sub = Submission.model_validate_json(
            (out.folder / "submission.json").read_text(encoding="utf-8")
        )
    total = live["calls"]["total"]
    if out.metadata["calls"] != {"total": total, "replayed": total, "live": 0}:
        raise Different("calls differ: not every recorded call replayed with none live")
    if out.metadata["cost_usd"] != live["cost_usd"]:
        raise Different("cost differs from the run metadata")
    sub = sub.model_copy(
        update={"system": sub.system.model_copy(update={"run_id": live["run_id"]})}
    )

    corpus = build_corpus(load(_world(target.equipment)))
    key_dir = ROOT / "answer_key" / target.equipment
    if target.package_world is None:
        scored = score(sub, load_key(key_dir), PageTexts(corpus))
        return with_metadata(scored, sub, corpus, key_dir)
    spec = load_package(ROOT / target.package_world)
    package_key = package_key_dir(ROOT / "answer_key", spec.id, spec.version)
    draft = render_draft(spec, corpus.eq, target.draft_rev)
    review = ReviewPackage.of(spec, draft, load_package_key(package_key))
    scored = score(sub, load_key(key_dir), PageTexts(corpus, extra=[draft]), package=review)
    return with_metadata(scored, sub, corpus, key_dir, package_key)


def _without_version(report: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in report.items() if k != FIELD}


def diff_paths(a: Any, b: Any, path: str = "") -> Iterator[str]:
    """The paths at which ``a`` and ``b`` differ (dev targets only: a path can name an item)."""
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b), key=str):
            if a.get(k, ...) != b.get(k, ...):
                yield from diff_paths(a.get(k), b.get(k), f"{path}.{k}" if path else str(k))
    elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for i, (x, y) in enumerate(zip(a, b, strict=True)):
            if x != y:
                yield from diff_paths(x, y, f"{path}[{i}]")
    else:
        yield path


def _stamped(text: str, old: str, version: str) -> str:
    """``text`` with its one ``"scorer_version": "<old>"`` set to ``version``."""
    field = f'"{FIELD}": "{old}"'
    if text.count(field) != 1:
        raise Different("the file does not hold exactly one scorer version")
    return text.replace(field, f'"{FIELD}": "{version}"')


def apply(
    fresh: Mapping[str, Any],
    report_path: Path,
    baseline_path: Path | None,
    *,
    version: str = SCORER_VERSION,
    write: bool = True,
    explain: bool = False,
) -> int:
    """Re-stamp ``report_path`` (and ``baseline_path``) with ``version`` when ``fresh`` equals
    the committed report apart from ``scorer_version``; otherwise write nothing."""
    fresh = json.loads(json.dumps(fresh))  # tuples as lists, as the committed JSON holds them
    report_text = report_path.read_text(encoding="utf-8")
    stored = json.loads(report_text)
    try:
        if _without_version(fresh) != _without_version(stored):
            if explain:
                for p in list(diff_paths(_without_version(stored), _without_version(fresh)))[:40]:
                    print(f"  differs: {p}")
            raise Different("the replayed report differs from the committed one")
        if fresh[FIELD] != version:
            raise Different("the scorer that ran is not the version to stamp")
        new_report = _stamped(report_text, stored[FIELD], version)
        if json.loads(new_report) != {**stored, FIELD: version}:
            raise Different("the re-stamped report changes more than the scorer version")
        new_baseline = None
        if baseline_path is not None:
            baseline_text = baseline_path.read_text(encoding="utf-8")
            committed = ratchet.read(baseline_path)
            try:
                derived = ratchet.from_report(fresh)
            except ratchet.BaselineError as e:
                raise Different("the replayed report cannot be a baseline") from e
            if committed.model_copy(update={FIELD: version}) != derived:
                raise Different("the committed baseline is not the replayed report's")
            new_baseline = _stamped(baseline_text, committed.scorer_version, version)
            if ratchet.Baseline.model_validate_json(new_baseline) != derived:
                raise Different("the re-stamped baseline changes more than the scorer version")
    except Different as e:
        print(f"different, nothing written: {e}")
        return DIFFERENT
    if write:
        report_path.write_text(new_report, encoding="utf-8", newline="\n")
        if baseline_path is not None and new_baseline is not None:
            baseline_path.write_text(new_baseline, encoding="utf-8", newline="\n")
        print(f"equal: re-stamped with scorer {version}")
    else:
        print("equal: nothing written (--check)")
    return EQUAL


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="restamp_scorer")
    parser.add_argument("target", choices=sorted(TARGETS))
    parser.add_argument("--check", action="store_true", help="compare only, write nothing")
    parser.add_argument("--explain", action="store_true", help="print differing paths (dev)")
    args = parser.parse_args(argv)
    target = TARGETS[args.target]
    held_out = split_of(target.equipment) != "dev"
    if held_out and args.explain:
        print("--explain is refused for a held-out target")
        return ERROR
    baseline = None if target.baseline is None else ROOT / target.baseline
    try:
        return apply(
            replay(target),
            ROOT / target.report,
            baseline,
            write=not args.check,
            explain=args.explain,
        )
    except Different as e:
        print(f"different, nothing written: {e}")
        return DIFFERENT
    except Exception:
        if not held_out:
            raise
        print("the replay or the scoring raised (message dropped)")
        return ERROR


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
