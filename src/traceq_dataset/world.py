"""Load world-data YAML and report how far it is from frozen.

Usage::

    uv run python -m traceq_dataset.world world/tp201.yaml

Prints the pending count, the intended Coverage distribution against the design
target, and, once nothing is pending, whether the decision table agrees with every
``intended_coverage`` and which judged values (requirement values, calibration readings)
still await human review. "frozen-ready"
needs all three. Exit code 1 on a schema error or a disagreement.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import yaml

from traceq_dataset.coverage import classify
from traceq_dataset.schema import CoverageClass, Equipment

TARGET_SHARE = {  # design section 6, TP-201
    CoverageClass.COVERED_BY_VENDOR: 0.40,
    CoverageClass.PARTIAL: 0.20,
    CoverageClass.SITE_ONLY: 0.15,
    CoverageClass.GAP: 0.20,
    CoverageClass.CONFLICT: 0.05,
}


def load(path: Path) -> Equipment:
    with path.open(encoding="utf-8") as f:
        return Equipment.model_validate(yaml.safe_load(f))


def disagreements(eq: Equipment) -> list[str]:
    """Requirements whose decision-table class differs from the intended one."""
    protocols = {p.doc_id: p for p in eq.protocols}
    vendors = {eq.vendor.id: eq.vendor}
    out = []
    for r in eq.requirements:
        got = classify(r, eq.tests, eq.designs, protocols, vendors)
        if got.coverage is not r.intended_coverage:
            out.append(f"{r.id}: intended {r.intended_coverage}, got {got.coverage} ({got.reason})")
    return out


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    eq = load(Path(argv[0]))
    n = len(eq.requirements)
    print(f"{eq.tag}: {n} requirements, {len(eq.tests)} test steps, {len(eq.scenarios)} scenarios")

    counts = Counter(r.intended_coverage for r in eq.requirements)
    for cls, share in TARGET_SHARE.items():
        print(f"  {cls:<18} {counts[cls]:>3}  ({counts[cls] / n:.0%}, target {share:.0%})")

    pending = eq.pending()
    if pending:
        print(f"pending: {len(pending)}")
        for p in pending:
            print(f"  - {p}")
        return 0

    bad = disagreements(eq)
    for line in bad:
        print(f"DISAGREE {line}")
    if bad:
        print(f"{len(bad)} disagreement(s)")
        return 1

    review, readings, risks = eq.unreviewed(), eq.unreviewed_results(), eq.unreviewed_risks()
    if review:
        print(f"awaiting human review: {len(review)} judged value(s) (* = no supporting quote)")
        for r in review:
            mark = " " if r.source.quote else "*"
            print(f"  {mark} {r.id} {r.param} [{r.source.drafted_by}]")
    if readings:
        print(f"awaiting human review: {len(readings)} calibration result table(s)")
        for i in readings:
            print(f"    {i.certificate.id} ({i.id}) [{i.certificate.results.drafted_by}]")
    if risks:
        ra = eq.risk_assessment
        assert ra is not None
        print(
            f"awaiting human review: {ra.doc_id} scores of {len(ra.rows)} FMEA rows and the "
            f"criticality threshold [{ra.drafted_by}]"
        )
    if review or readings or risks:
        return 0
    print("frozen-ready")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
