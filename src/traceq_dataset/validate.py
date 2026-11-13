"""Semantic validator for rendered documents (design section 8, "CI").

CI re-renders and checks meaning, not bytes: every placed string the answer key relies on
must appear in the extracted text of the page the renderer says it is on. A handwritten
entry must also appear inside its recorded bounding box, which the OCR answer key uses. In a
spreadsheet, every placed string must be the value of its recorded cell.
"""

from __future__ import annotations

import io
import re
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

import numpy as np
import pypdfium2 as pdfium
from openpyxl import load_workbook
from openpyxl.utils.cell import coordinate_from_string
from PIL import Image, ImageDraw
from pypdf import PdfReader

from traceq_dataset.degrade import Scanned
from traceq_dataset.render import Box, Rendered, fmt_number
from traceq_dataset.schema import Document

if TYPE_CHECKING:
    from traceq_dataset.corpus import Corpus

_SPACE = re.compile(r"\s+")
BOX_TOLERANCE = 1.0
"""pt added on every side: glyph outlines may touch the measured box."""


def normalise(text: str) -> str:
    """Collapse whitespace, so line breaks inside table cells do not matter."""
    return _SPACE.sub(" ", text).strip()


def page_texts(pdf: bytes) -> list[str]:
    return [normalise(p.extract_text()) for p in PdfReader(io.BytesIO(pdf)).pages]


def text_in_box(pdf: pdfium.PdfDocument, page: int, box: Box) -> str:
    """Text whose characters lie inside ``box`` (top-left origin, pt) on ``page`` (1-based)."""
    p = pdf[page - 1]
    height, t = p.get_height(), BOX_TOLERANCE
    return normalise(
        p.get_textpage().get_text_bounded(
            left=box.x - t,
            bottom=height - box.y - box.h - t,
            right=box.x + box.w + t,
            top=height - box.y + t,
        )
    )


MIN_INK = 0.05
"""Least share of dark pixels inside a handwritten quad on a scan (measured ≥ 0.11)."""


def scan_problems(scanned: Scanned) -> list[str]:
    """A scan must have no text layer, and every handwritten quad must lie on its page
    and hold ink. The quad geometry itself is tested against Pillow's rotation."""
    reader = PdfReader(io.BytesIO(scanned.pdf))
    out = [
        f"{scanned.filename} page {i}: has a text layer"
        for i, p in enumerate(reader.pages, 1)
        if p.extract_text().strip()
    ]
    pdf, scale = pdfium.PdfDocument(scanned.pdf), scanned.dpi / 72
    # pypdfium2's stub types `scale` as int; the library takes a float (dpi / 72).
    bitmaps = [pdf[i].render(scale=scale) for i in range(len(pdf))]  # pyright: ignore[reportArgumentType]
    pages = [b.to_pil().convert("L") for b in bitmaps]
    for key, placed in scanned.placed.items():
        if placed.quad is None:
            continue
        page = pages[placed.page - 1]
        corners = [(x * scale, y * scale) for x, y in placed.quad]
        if not all(0 <= x <= page.width and 0 <= y <= page.height for x, y in corners):
            out.append(f"{scanned.filename} {key}: quad off page {placed.page}")
            continue
        mask = Image.new("1", page.size)
        ImageDraw.Draw(mask).polygon(corners, fill=1)
        ink = np.asarray(page)[np.asarray(mask)] < 170
        if ink.mean() < MIN_INK:
            out.append(f"{scanned.filename} {key}: no ink in its quad on page {placed.page}")
    return out


def cell_texts(xlsx: bytes) -> dict[tuple[str, str], str]:
    """Every non-empty cell of a workbook as text, keyed by (sheet, cell)."""
    wb = load_workbook(io.BytesIO(xlsx), read_only=True)
    return {
        (ws.title, c.coordinate): str(c.value)
        for ws in wb.worksheets
        for row in ws.iter_rows()
        for c in row
        if c.value is not None and hasattr(c, "coordinate")
    }


def missing_text(rendered: Rendered) -> list[str]:
    """Placed strings not found on their recorded page, or outside their recorded box; in a
    spreadsheet, not the value of their recorded cell."""
    if rendered.format == "xlsx":
        cells = cell_texts(rendered.data)
        return [
            f"{rendered.filename} {key}: not in {p.sheet}!{p.cell}"
            for key, p in rendered.placed.items()
            if cells.get((p.sheet or "", p.cell or "")) != p.text
        ]
    pages = page_texts(rendered.pdf)
    pdf = pdfium.PdfDocument(rendered.pdf)
    out = []
    for key, placed in rendered.placed.items():
        where = f"{rendered.filename} {key}"
        text = normalise(placed.text)
        if not 1 <= placed.page <= len(pages):
            out.append(f"{where}: page {placed.page} out of range")
        elif text not in pages[placed.page - 1]:
            out.append(f"{where}: text not on page {placed.page}")
        elif placed.box and text not in text_in_box(pdf, placed.page, placed.box):
            out.append(f"{where}: text not in its box on page {placed.page}")
    return out


# --- Answer key (design section 8, "CI") -----------------------------------------------

RISK_SCORES = ("severity", "occurrence", "detection", "rpn", "critical")
"""Fields of an answer-key ``risk`` entry that are cells of the FMEA row."""

QUAD_TOLERANCE = 0.01
"""pt: a committed quad may differ from the re-derived one by rounding only."""


def answer_key_problems(key: Mapping[str, Any], corpus: Corpus) -> list[str]:
    """Check an answer key as loaded from disk against a freshly rendered corpus.

    Every value must appear on the page it is cited on (scans: in the born-digital render
    behind the pixels), every handwritten location must carry the quad of the scan, every
    planned location must name a document that is really not rendered yet, every probe's lure
    must be on its page (and an evidence probe's requirement have no Evidence), and the list
    of documents that should exist must match the corpus.
    """
    check = _KeyCheck(corpus)
    for r in key["requirements.yaml"]:
        src = r["source"]
        check.on_page(r["id"], src, r["text"])
        check.value_in_text(r["id"], src["doc"], src["rev"], r["value"], r["text"])
        for old in r.get("superseded", []):
            where = {"doc": src["doc"], "rev": old["rev"], "page": old["page"]}
            check.on_page(f"{r['id']} rev {old['rev']}", where, old["text"])
            check.value_in_text(r["id"], src["doc"], old["rev"], old["value"], old["text"])
        for ev in r["evidence"]:
            name = f"{r['id']} {ev['step']}"
            check.on_page(name, ev, ev["observed"])
            check.on_page(name, ev, ev["acceptance"])
            if (ev["doc"], ev["rev"]) in corpus.scanned:
                check.location(
                    name, {**ev, "field": f"{ev['step']}.observed", "text": ev["observed"]}
                )
        for ev in r["design_evidence"]:
            check.location(f"{r['id']} {ev['doc']}", {"doc": ev["doc"], "rev": 0, **ev})
        if "risk" in r:
            check.risk(r["id"], r["risk"])
    for d in key["defects.yaml"]:
        for loc in d["locations"]:
            check.location(d["id"], loc)
    for a in key["ambiguous.yaml"]:
        check.location(a["id"], a["location"])
    reqs = {r["id"]: r for r in key["requirements.yaml"]}
    for p in key["probes.yaml"]:
        r = reqs.get(p["requirement"])
        if r is None:
            check.out.append(f"{p['id']}: unknown requirement {p['requirement']}")
            continue
        if p["source"] != {k: r["source"][k] for k in ("doc", "rev", "page")}:
            check.out.append(f"{p['id']}: source is not where {r['id']} is")
        if p["absent"] == "evidence" and r["evidence"]:
            check.out.append(f"{p['id']}: {r['id']} has Evidence in the key")
        for loc in p["lures"]:
            check.location(f"{p['id']} lure", loc)
    check.documents(key["documents.yaml"])
    for scan in key["ocr.yaml"]:
        doc = (scan["doc"], scan["rev"])
        if doc not in corpus.scanned:
            check.out.append(f"ocr {scan['doc']} rev {scan['rev']}: not a scan in the corpus")
            continue
        handwritten = {k for k, p in corpus.scanned[doc].placed.items() if p.quad}
        listed = {e["field"] for e in scan["entries"]}
        if listed != handwritten:
            check.out.append(f"ocr {scan['doc']}: entries differ: {sorted(listed ^ handwritten)}")
        for e in scan["entries"]:
            check.location(f"ocr {scan['doc']}", {"doc": scan["doc"], "rev": scan["rev"], **e})
    return check.out


class _KeyCheck:
    def __init__(self, corpus: Corpus) -> None:
        self.corpus = corpus
        self.out: list[str] = []
        self._pages: dict[tuple[str, int], list[str]] = {}

    def pages(self, doc: tuple[str, int]) -> list[str]:
        if doc not in self._pages:
            self._pages[doc] = page_texts(self.corpus.rendered[doc].pdf)
        return self._pages[doc]

    def on_page(self, name: str, where: Mapping[str, Any], text: str) -> bool:
        doc = (where["doc"], where["rev"])
        if doc not in self.corpus.rendered:
            self.out.append(f"{name}: {doc[0]} rev {doc[1]} not in the corpus")
            return False
        pages, page = self.pages(doc), where.get("page")
        if not isinstance(page, int) or not 1 <= page <= len(pages):
            self.out.append(f"{name}: {doc[0]} has no page {page}")
            return False
        if normalise(text) not in pages[page - 1]:
            self.out.append(f"{name}: {text!r} not on {doc[0]} rev {doc[1]} page {page}")
            return False
        return True

    def value_in_text(self, name: str, doc: str, rev: int, value: Mapping, text: str) -> None:
        """The normalised value, formatted in the document language, is in the sentence."""
        lang = self.corpus.document((doc, rev)).language
        if value["type"] == "range":
            tokens = [fmt_number(value[b], lang) for b in ("min", "max") if b in value]
        elif value["type"] == "one_of":
            tokens = list(value["allowed"])
        else:
            tokens = []
        self.out += [f"{name}: value {t!r} not in {text!r}" for t in tokens if t not in text]

    def risk(self, req: str, risk: Mapping[str, Any]) -> None:
        """An FMEA row: each score and the criticality are the values of the cells the
        renderer placed, all on one row of the named sheet."""
        doc = (risk["doc"], risk["rev"])
        rendered = self.corpus.rendered.get(doc)
        if rendered is None or rendered.format != "xlsx":
            self.out.append(f"{req} risk: {doc[0]} rev {doc[1]} is not a spreadsheet in the corpus")
            return
        cells = cell_texts(rendered.data)
        expected = {**{k: risk[k] for k in RISK_SCORES[:-1]}, "critical": risk["text"]}
        for name, value in expected.items():
            placed = rendered.placed.get(f"{req}.{name}")
            if placed is None or placed.sheet != risk["sheet"] or placed.cell is None:
                self.out.append(f"{req} risk: no {name} cell on sheet {risk['sheet']!r}")
            elif coordinate_from_string(placed.cell)[1] != risk["row"]:
                self.out.append(f"{req} risk: {name} is not on row {risk['row']}")
            elif cells.get((risk["sheet"], placed.cell)) != str(value):
                self.out.append(f"{req} risk: {name} is not {value!r} in {placed.cell}")
        if (risk["text"] == "Ya") != risk["critical"]:
            self.out.append(f"{req} risk: critical {risk['critical']} but marked {risk['text']!r}")

    def location(self, name: str, loc: Mapping[str, Any]) -> None:
        doc = (loc["doc"], loc["rev"])
        if loc.get("status") == "planned":
            if doc[0] in {d for d, _ in self.corpus.rendered}:
                self.out.append(f"{name}: {doc[0]} is rendered now; re-derive the answer key")
            return
        if not self.on_page(name, loc, loc["text"]):
            return
        key = loc.get("field")
        if key is None:
            return
        placed = self.corpus.rendered[doc].placed.get(key)
        if placed is None or (placed.page, placed.text) != (loc["page"], loc["text"]):
            self.out.append(f"{name}: {key} is not {loc['text']!r} on page {loc['page']}")
            return
        scanned = self.corpus.scanned.get(doc)
        expected = scanned.placed[key].quad if scanned else None
        quad = loc.get("quad")
        if expected is None:
            if quad is not None:
                self.out.append(f"{name}: {key} has a quad but is not a handwritten scan entry")
        elif quad is None:
            self.out.append(f"{name}: {key} is handwritten on a scan but has no quad")
        elif any(
            abs(a - b) > QUAD_TOLERANCE
            for p, q in zip(quad, expected, strict=True)
            for a, b in zip(p, q, strict=True)
        ):
            self.out.append(f"{name}: {key} quad does not match the scan")

    def documents(self, required: list[Mapping[str, Any]]) -> None:
        rendered: dict[str, set[tuple[int, str]]] = {}
        for doc, rev in self.corpus.rendered:
            if self.corpus.document((doc, rev)).type in Document.GOVERNING_TYPES:
                continue  # site-wide, not part of the Equipment's package
            rendered.setdefault(doc, set()).add((rev, self.corpus.filename((doc, rev))))
        listed = set()
        for d in required:
            listed.add(d["id"])
            files = {(f["rev"], f["file"]) for f in d.get("files", [])}
            if d["status"] == "in_corpus" and files != rendered.get(d["id"]):
                self.out.append(f"documents {d['id']}: files differ from the corpus")
            if d["status"] != "in_corpus" and d["id"] in rendered:
                self.out.append(f"documents {d['id']}: {d['status']} but rendered")
        self.out += [
            f"documents: {d} rendered but not listed" for d in sorted(set(rendered) - listed)
        ]
