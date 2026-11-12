"""Check every quoted source in a world file against its live page (local use only).

    uv run python scripts/verify_quotes.py world/tp201.yaml

For each requirement whose source has a URL, the page (HTML or PDF) is downloaded and
the quote must be found in its text, exactly or by fuzzy match (ratio >= 0.9, the same
threshold as citation scoring in design section 9). The value-in-quote check runs in
the schema itself, so it also runs in CI; this script needs the network, so it does not.

Exit code 1 if any quote is not found or a page cannot be read.
"""

from __future__ import annotations

import io
import re
import sys
import unicodedata
import urllib.request
from difflib import SequenceMatcher
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from traceq_dataset.world import load

THRESHOLD = 0.9
USER_AGENT = "traceq-dataset-quote-check/0.1"
DASHES = "".join(map(chr, [*range(0x2010, 0x2016), 0x2212]))  # hyphens, dashes, minus
QUOTES = "".join(map(chr, [0x2018, 0x2019, 0x201C, 0x201D]))  # curly quotes


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: object) -> None:
        if tag in {"script", "style"}:
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def normalise(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(f"[{DASHES}]", "-", text)
    text = re.sub(f"[{QUOTES}]", "'", text)
    return re.sub(r"\s+", " ", text).strip()


def page_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = resp.read()
        ctype = resp.headers.get("Content-Type", "")
    if "pdf" in ctype or body[:5] == b"%PDF-":
        from pypdf import PdfReader

        return "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(body)).pages)
    parser = _Text()
    parser.feed(body.decode(resp.headers.get_content_charset() or "utf-8", errors="replace"))
    return " ".join(parser.parts)


def best_ratio(quote: str, text: str) -> float:
    """1.0 for an exact match, else the best fuzzy ratio over quote-sized windows."""
    if quote in text:
        return 1.0
    size, step = len(quote), max(1, len(quote) // 4)
    best = 0.0
    for start in range(0, max(1, len(text) - size + 1), step):
        window = text[start : start + size + step]
        m = SequenceMatcher(None, quote, window, autojunk=False)
        if m.quick_ratio() > best:
            best = max(best, m.ratio())
    return best


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    eq = load(Path(argv[0]))
    cache: dict[str, str] = {}
    failures = checked = 0
    for r in eq.requirements:
        src = r.source
        if src.url is None or src.quote is None:
            continue
        url = str(src.url)
        try:
            if url not in cache:
                cache[url] = normalise(page_text(url))
        except Exception as exc:  # report and continue with the next source
            print(f"ERROR {r.id}: cannot read {url}: {exc}")
            failures += 1
            continue
        checked += 1
        ratio = best_ratio(normalise(src.quote), cache[url])
        status = "ok  " if ratio >= THRESHOLD else "MISS"
        failures += ratio < THRESHOLD
        print(f"{status} {r.id} ratio={ratio:.2f} {src.ref}")
    print(f"{checked} quote(s) checked, {failures} problem(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
