"""Score a recorded submission (replay) against an Equipment's answer key.

Usage::

    uv run python -m traceq_eval world/tp201.yaml submission.json [--key answer_key] [--out report]

Exit code 0 when every gate passes, 1 when a gate fails, 2 when the submission is invalid.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pydantic import ValidationError

from traceq_dataset.answer_key import load_key
from traceq_dataset.corpus import build_corpus
from traceq_dataset.world import load
from traceq_eval.citations import PageTexts
from traceq_eval.report import with_metadata, write
from traceq_eval.score import score
from traceq_eval.submission import Submission


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="traceq_eval")
    parser.add_argument("world", type=Path)
    parser.add_argument("submission", type=Path)
    parser.add_argument("--key", type=Path, default=Path("answer_key"))
    parser.add_argument("--out", type=Path, default=Path("report"))
    args = parser.parse_args(argv)

    try:
        sub = Submission.model_validate_json(args.submission.read_text(encoding="utf-8"))
    except ValidationError as e:
        print(f"invalid submission: {e}", file=sys.stderr)
        return 2
    eq = load(args.world)
    corpus = build_corpus(eq)
    key_dir = args.key / eq.tag
    report = with_metadata(score(sub, load_key(key_dir), PageTexts(corpus)), sub, corpus, key_dir)
    write(report, args.out)
    gates = report["gates"]
    print(f"gates {'PASS' if gates['passed'] else 'FAIL'}; report in {args.out}")
    for name, g in gates.items():
        if name != "passed" and not g["passed"]:
            print(f"  {name}: {g['count']}")
    return 0 if gates["passed"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
