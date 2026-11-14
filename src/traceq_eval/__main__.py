"""Score a recorded submission (replay) against an Equipment's answer key.

Usage::

    uv run python -m traceq_eval promote runs/<run id> --recordings recordings/haiku-r<n>
        [--baseline [PATH]]  (see ``traceq_eval.promote``)

    uv run python -m traceq_eval world/tp201.yaml submission.json [--key answer_key]
        [--out report] [--baseline baselines/TP-201.json] [--write-baseline PATH]

``--baseline`` adds the ratchet against an accepted baseline; ``--write-baseline`` writes
this run as a baseline candidate (refused when a gate fails), to be accepted through a PR.

Exit code 0 when every gate (and the ratchet, if asked) passes, 1 when a gate or the ratchet
fails, 2 when the submission or the baseline is invalid.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pydantic import ValidationError

from traceq_dataset.answer_key import load_key
from traceq_dataset.corpus import build_corpus
from traceq_dataset.world import load
from traceq_eval import ratchet
from traceq_eval.citations import PageTexts
from traceq_eval.report import with_metadata, write
from traceq_eval.score import score
from traceq_eval.submission import Submission


def main(argv: list[str]) -> int:
    if argv[:1] == ["promote"]:
        from traceq_eval import promote

        return promote.main(argv[1:])
    parser = argparse.ArgumentParser(prog="traceq_eval")
    parser.add_argument("world", type=Path)
    parser.add_argument("submission", type=Path)
    parser.add_argument("--key", type=Path, default=Path("answer_key"))
    parser.add_argument("--out", type=Path, default=Path("report"))
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--write-baseline", type=Path)
    args = parser.parse_args(argv)

    try:
        sub = Submission.model_validate_json(args.submission.read_text(encoding="utf-8"))
        baseline = ratchet.read(args.baseline) if args.baseline else None
    except (ValidationError, ratchet.BaselineError) as e:
        print(f"invalid input: {e}", file=sys.stderr)
        return 2
    eq = load(args.world)
    corpus = build_corpus(eq)
    key_dir = args.key / eq.tag
    report = with_metadata(score(sub, load_key(key_dir), PageTexts(corpus)), sub, corpus, key_dir)
    if baseline:
        try:
            report["ratchet"] = ratchet.compare(baseline, report)
        except ratchet.BaselineError as e:
            print(f"invalid input: {e}", file=sys.stderr)
            return 2
    write(report, args.out)

    gates = report["gates"]
    print(f"gates {'PASS' if gates['passed'] else 'FAIL'}; report in {args.out}")
    for name, g in gates.items():
        if name != "passed" and not g["passed"]:
            print(f"  {name}: {g['count']}")
    passed = gates["passed"]
    if baseline:
        r = report["ratchet"]
        passed &= r["passed"]
        print(f"ratchet {'PASS' if r['passed'] else 'FAIL'} against {args.baseline}")
        for line in [*r["reasons"], *r["failing"], *(f"warning: {w}" for w in r["warnings"])]:
            print(f"  {line}")
    if args.write_baseline:
        if not gates["passed"]:
            print("no baseline written: a run that fails a gate cannot be one", file=sys.stderr)
        else:
            ratchet.dump(ratchet.from_report(report), args.write_baseline)
            print(f"baseline candidate in {args.write_baseline}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
