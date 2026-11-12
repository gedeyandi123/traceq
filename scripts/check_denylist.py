"""Fail if any file mentions a denylisted name.

Terms come from three places, matched case-insensitively on word boundaries:

- ``denylist/public.txt``: real equipment vendor names (committed).
- ``.denylist.local``: private terms, one per line (gitignored, never committed).
- ``DENYLIST`` env var: private terms, newline- or comma-separated (CI secret).

Private terms are never printed, so CI logs stay clean.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

PUBLIC_LIST = Path("denylist/public.txt")
LOCAL_LIST = Path(".denylist.local")
SKIP = {PUBLIC_LIST.as_posix(), LOCAL_LIST.as_posix()}


def _read_terms(text: str, *, commas: bool = False) -> list[str]:
    """One term per line; ``#`` starts a comment. Env values may also use commas."""
    terms = []
    for line in text.splitlines():
        line = line.split("#", 1)[0]
        for term in line.split(",") if commas else [line]:
            if term.strip():
                terms.append(term.strip())
    return terms


def _compile(term: str) -> re.Pattern[str]:
    return re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", re.IGNORECASE)


def load_terms() -> list[tuple[re.Pattern[str], str]]:
    """Return (pattern, label) pairs; private labels hide the term."""
    pairs = []
    if PUBLIC_LIST.exists():
        for term in _read_terms(PUBLIC_LIST.read_text(encoding="utf-8")):
            pairs.append((_compile(term), f"vendor name '{term}'"))
    private = []
    if LOCAL_LIST.exists():
        private += _read_terms(LOCAL_LIST.read_text(encoding="utf-8"))
    private += _read_terms(os.environ.get("DENYLIST", ""), commas=True)
    for i, term in enumerate(dict.fromkeys(private), start=1):
        pairs.append((_compile(term), f"private term #{i}"))
    if not private:
        print(
            "warning: no private denylist (.denylist.local or DENYLIST)",
            file=sys.stderr,
        )
    return pairs


def scan(paths: list[str], terms: list[tuple[re.Pattern[str], str]]) -> int:
    hits = 0
    for name in paths:
        path = Path(name)
        if path.as_posix() in SKIP or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue  # binary file
        candidates = [path.as_posix(), *text.splitlines()]
        for lineno, line in enumerate(candidates):
            for pattern, label in terms:
                if pattern.search(line):
                    where = (
                        f"{path.as_posix()}:{lineno}"
                        if lineno
                        else f"{path.as_posix()} (file name)"
                    )
                    print(f"{where}: {label}")
                    hits += 1
    return hits


def main(argv: list[str]) -> int:
    hits = scan(argv, load_terms())
    if hits:
        print(f"denylist: {hits} hit(s)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
