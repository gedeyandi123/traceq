"""Brings the demo to a known state, and resets it when run again (spec #105, ticket #115).

    uv run python scripts/demo.py CORPUS_DIR [--no-compose] [--recordings DIR] [--runs DIR]

The Equipment is fixed here: demo data is TP-201 (dev) only and the held-out Equipment is
never loaded. System code names no Equipment, so the choice lives in this script.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from traceq.app.demo import DemoSettings, run_demo

EQUIPMENT = "TP-201"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    p.add_argument("corpus", type=Path, help="the extracted corpus release 0.1.0")
    # Unset options keep DemoSettings' defaults, so they are written in one place.
    p.add_argument("--recordings", type=Path)
    p.add_argument("--runs", type=Path)
    p.add_argument("--issuer-port", type=int)
    p.add_argument("--api-port", type=int)
    p.add_argument("--no-compose", action="store_true", help="Postgres already runs")
    a = p.parse_args()
    given = {
        "recordings": a.recordings,
        "runs": a.runs,
        "issuer_port": a.issuer_port,
        "api_port": a.api_port,
    }
    return run_demo(
        DemoSettings(
            corpus=a.corpus,
            equipment=EQUIPMENT,
            compose=not a.no_compose,
            **{k: v for k, v in given.items() if v is not None},
        )
    )


if __name__ == "__main__":
    sys.exit(main())
