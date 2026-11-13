"""OCR of handwritten entries on scans (design section 6, "OCR locations"; section 9).

The answer key's ``ocr.yaml`` holds every handwritten entry on a scan with the text the
renderer drew and its quad after the scan's skew, so OCR accuracy is measured without manual
annotation. A submission hands in what it read as ``ocr`` entries: document, revision, page,
text and, optionally, the quad it read it from.

Matching, within the same document, revision and page, one-to-one:

1. **By quad:** a submitted quad whose axis-aligned box overlaps an expected one with
   IoU ≥ 0.5 (skew is at most 2°, so the boxes of the two quads are close enough). Greedy by
   IoU, then by CER.
2. **By text:** entries left over, with or without a quad, are paired by the lowest CER, if
   it is ≤ 0.5. A system that reads well but places boxes badly is still scored on reading,
   and leaving out the quad gains nothing: ``localisation_rate`` counts quad matches only.

Text is compared verbatim after NFKC and whitespace collapse, case-sensitive. Numbers are
**not** normalised: ``122.400`` and ``1.500`` are transcribed as written, and the decimal or
thousands separator is a character like any other. Reading the value (1500 or 1.5) is the
ambiguous-value scenario S7, scored in ``requirements`` and ``ambiguous``, not here.

An overwritten original (``<field>.original``, S1) is drawn under the final value and is no
longer legible, so it is not an expected entry. Reading it in place of the final value is a
misread, flagged ``read_overwritten_original``.

CER sums edit distances over the sum of expected lengths; an expected entry nothing matched
counts as fully deleted, so an empty submission scores CER 1.0. Submitted entries that match
nothing are reported (``unmatched_entries``), not scored: the key lists handwriting only,
and a system that also transcribes a stamp is not wrong. OCR errors are not fabrication:
nothing here is a gate.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from traceq_eval.citations import norm
from traceq_eval.submission import OcrEntry, Submission

MIN_IOU = 0.5
MAX_TEXT_CER = 0.5
ORIGINAL = ".original"
KINDS = ("number", "date", "id", "text")

_DATE = re.compile(r"\d{1,2}/\d{1,2}/\d{4}")
_NUMBER = re.compile(r"\d[\d.,]*(\s.*)?")


def kind(text: str) -> str:
    """``date`` (02/05/2026), ``number`` (a measurement: 122.400 tablets/h, 20,4 kN),
    ``id`` (letters and digits: TACH-07, RTP36-25-0471) or ``text`` (Lulus, a name)."""
    t = norm(text)
    if _DATE.fullmatch(t):
        return "date"
    if _NUMBER.fullmatch(t):
        return "number"
    if re.search(r"\d", t) and re.search(r"[A-Za-z]", t):
        return "id"
    return "text"


def edits(a: str, b: str) -> int:
    """Levenshtein distance (insert, delete, substitute; each costs 1)."""
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def cer(ref: str, hyp: str) -> float:
    r, h = norm(ref), norm(hyp)
    return edits(r, h) / len(r) if r else float(bool(h))


def _box(quad: Sequence[Sequence[float]]) -> tuple[float, float, float, float]:
    xs, ys = [p[0] for p in quad], [p[1] for p in quad]
    return min(xs), min(ys), max(xs), max(ys)


def iou(a: Sequence[Sequence[float]], b: Sequence[Sequence[float]]) -> float:
    """IoU of the axis-aligned boxes of two quads."""
    ax0, ay0, ax1, ay1 = _box(a)
    bx0, by0, bx1, by1 = _box(b)
    w, h = min(ax1, bx1) - max(ax0, bx0), min(ay1, by1) - max(ay0, by0)
    if w <= 0 or h <= 0:
        return 0.0
    inter = w * h
    return inter / ((ax1 - ax0) * (ay1 - ay0) + (bx1 - bx0) * (by1 - by0) - inter)


def _ratio(n: float, d: float) -> float | None:
    return round(n / d, 4) if d else None


def expected_entries(key: Mapping[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Every legible handwritten entry, with its document's scan level."""
    return [
        {"doc": d["doc"], "rev": d["rev"], "level": d["level"], **e}
        for d in key["ocr.yaml"]
        for e in d["entries"]
        if not e["field"].endswith(ORIGINAL)
    ]


def _match(
    expected: list[dict[str, Any]], submitted: Sequence[OcrEntry]
) -> dict[int, tuple[int, str, float | None]]:
    """Expected index → (submitted index, ``quad`` or ``text``, IoU)."""
    out: dict[int, tuple[int, str, float | None]] = {}
    used: set[int] = set()
    pairs = []
    for i, e in enumerate(expected):
        for j, s in enumerate(submitted):
            if s.quad is None or (s.doc, s.rev, s.page) != (e["doc"], e["rev"], e["page"]):
                continue
            v = iou(e["quad"], s.quad)
            if v >= MIN_IOU:
                pairs.append((-v, cer(e["text"], s.text), i, j))
    for neg_iou, _, i, j in sorted(pairs):
        if i not in out and j not in used:
            out[i] = (j, "quad", round(-neg_iou, 4))
            used.add(j)
    pairs = []
    for i, e in enumerate(expected):
        if i in out:
            continue
        for j, s in enumerate(submitted):
            if j in used or (s.doc, s.rev, s.page) != (e["doc"], e["rev"], e["page"]):
                continue
            c = cer(e["text"], s.text)
            if c <= MAX_TEXT_CER:
                pairs.append((c, i, j))
    for _, i, j in sorted(pairs):
        if i not in out and j not in used:
            out[i] = (j, "text", None)
            used.add(j)
    return out


def score_ocr(sub: Submission, key: Mapping[str, list[dict[str, Any]]]) -> dict[str, Any]:
    expected = expected_entries(key)
    originals = {
        (d["doc"], d["rev"], e["page"], e["field"][: -len(ORIGINAL)]): e["text"]
        for d in key["ocr.yaml"]
        for e in d["entries"]
        if e["field"].endswith(ORIGINAL)
    }
    matched = _match(expected, sub.ocr)
    items = []
    for i, e in enumerate(expected):
        j, by, overlap = matched.get(i, (None, None, None))
        got = None if j is None else sub.ocr[j].text
        ref = norm(e["text"])
        n = edits(ref, norm(got)) if got is not None else len(ref)
        original = originals.get((e["doc"], e["rev"], e["page"], e["field"]))
        items.append(
            {
                "doc": e["doc"],
                "rev": e["rev"],
                "page": e["page"],
                "field": e["field"],
                "kind": kind(e["text"]),
                "level": e["level"],
                "expected": e["text"],
                "got": got,
                "matched_by": by,
                "iou": overlap,
                "edits": n,
                "chars": len(ref),
                "exact": got is not None and norm(got) == ref,
                "read_overwritten_original": got is not None
                and original is not None
                and norm(got) == norm(original),
            }
        )

    def group(attr: str, values: Sequence[str]) -> tuple[dict, dict]:
        c, x = {}, {}
        for v in values:
            sel = [i for i in items if i[attr] == v]
            c[v] = _ratio(sum(i["edits"] for i in sel), sum(i["chars"] for i in sel))
            x[v] = _ratio(sum(i["exact"] for i in sel), len(sel))
        return c, x

    levels = sorted({d["level"] for d in key["ocr.yaml"]})
    cer_by_kind, exact_by_kind = group("kind", KINDS)
    cer_by_level, _ = group("level", levels)
    n = len(items)
    return {
        "metrics": {
            "entries": n,
            "submitted": len(sub.ocr),
            "matched": len(matched),
            "entry_recall": _ratio(len(matched), n),
            "localisation_rate": _ratio(sum(i["matched_by"] == "quad" for i in items), n),
            "exact_match_rate": _ratio(sum(i["exact"] for i in items), n),
            "cer": _ratio(sum(i["edits"] for i in items), sum(i["chars"] for i in items)),
            "cer_by_kind": cer_by_kind,
            "exact_match_by_kind": exact_by_kind,
            "cer_by_level": cer_by_level,
            "unmatched_entries": len(sub.ocr) - len(matched),
            "read_overwritten_original": sum(i["read_overwritten_original"] for i in items),
        },
        "items": items,
    }
