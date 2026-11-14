"""Render world data to born-digital PDF with Typst (design section 8).

Python formats every string (numbers and dates in the document language), so the
expected text is known exactly; the Typst templates in ``templates/`` only lay it out.
Output is deterministic for a given T0: no system fonts (Typst's bundled fonts plus the
OFL handwriting font in ``fonts/``) and PDF metadata dates fixed to the document's issue
date.

Paper documents (the SAT, material and calibration certificates) are rendered born-digital
with their handwritten entries drawn in a handwriting font, and each entry's bounding box
recorded (:class:`Box`). Scanning them (rasterise, skew, noise, JPEG) is the degrader's
job: a separate step that only transforms pixels and those boxes.

Design facts (``Equipment.designs``) are placed where :func:`design_field` says, so the
answer key can locate them on the datasheet, the functional spec and the material
certificate.

The risk assessment is a spreadsheet (XLSX, openpyxl), not a PDF: its placed strings carry
a sheet and cell instead of a box, and its bytes are fixed by setting every zip and
document-property date to the issue date.

Usage::

    uv run python -m traceq_dataset.render world/tp201.yaml [--t0 YYYY-MM-DD] [--out dist]

writes ``dist/t0-<T0>/<tag>/*.pdf`` (and ``*.xlsx``) and the corpus ``manifest.json``.
"""

from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import re
import sys
import zipfile
import zlib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import typst
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.worksheet import Worksheet

from traceq_dataset.coverage import meets
from traceq_dataset.schema import (
    Correction,
    DesignEvidence,
    Document,
    Equipment,
    NumberObs,
    Observation,
    OneOfSpec,
    Person,
    PresentObs,
    PresentSpec,
    RangeObs,
    RangeSpec,
    Requirement,
    Spec,
    TextObs,
)

TEMPLATES = Path(__file__).parent / "templates"
FONTS = Path(__file__).parent / "fonts"
EVAL_T0 = dt.date(2026, 6, 1)
"""Fixed T0 of the eval corpus (design section 4, "Dates")."""

EN_DASH = "\N{EN DASH}"
TIMES = "\N{MULTIPLICATION SIGN}"


class RenderError(ValueError):
    """World data cannot be rendered (pending values, unknown document)."""


@dataclass(frozen=True)
class Box:
    """Bounding box on the page in pt, origin top-left (Typst's coordinates)."""

    x: float
    y: float
    w: float
    h: float


@dataclass(frozen=True)
class Placed:
    """A string the renderer drew, and the page it is on (1-based).

    ``box`` is set for handwritten entries: the OCR answer key needs where they are. In a
    spreadsheet, ``page`` is the sheet's position and ``sheet`` / ``cell`` name the cell.
    """

    page: int
    text: str
    box: Box | None = None
    sheet: str | None = None
    cell: str | None = None

    @property
    def handwritten(self) -> bool:
        return self.box is not None


@dataclass(frozen=True)
class Rendered:
    doc_id: str
    rev: int
    issued: dt.date
    """Issue date, also the PDF (or XLSX) metadata date."""
    data: bytes
    placed: Mapping[str, Placed]
    """Keyed by requirement id (URS), ``<step>.acceptance`` / ``<step>.observed`` (FAT,
    SAT), a handwritten field (SAT, e.g. ``serial``, ``SAT-01.observed.original``), a design
    fact (:func:`design_field`), a certificate field (``valid_until``) or a risk-assessment
    cell (``URS-TP201-002.severity``)."""
    format: Literal["pdf", "xlsx"] = "pdf"

    @property
    def pdf(self) -> bytes:
        if self.format != "pdf":
            raise RenderError(f"{self.filename} is not a PDF")
        return self.data

    @property
    def filename(self) -> str:
        return f"{self.doc_id}_rev{self.rev}.{self.format}"


# --- Formatting ---------------------------------------------------------------------


def fmt_number(value: float, lang: str) -> str:
    """``120000`` → ``120.000`` (id) / ``120,000`` (en); ``0.8`` → ``0,8`` (id)."""
    text = f"{value:,.10g}"
    return text.translate(str.maketrans(",.", ".,")) if lang == "id" else text


DECIMAL_POINT = {"en": ".", "id": ","}
_GROUPED = re.compile(r"\d{1,3}([.,])\d{3}(?:\s+.+)?")


def reads_two_ways(printed: str, lang: str) -> bool:
    """The ambiguity rule (design section 6): one ``.`` or ``,`` before exactly three digits,
    where that separator is the decimal point of the document's language. A writer of the
    other convention may have meant thousands, so ``1.500 rpm`` on an English form is 1500 or
    1.5. As the grouping separator (``120.000`` in Indonesian) it reads one way."""
    m = _GROUPED.fullmatch(printed.strip())
    return m is not None and m[1] == DECIMAL_POINT[lang]


def awaiting_confirmation(eq: Equipment) -> frozenset[str]:
    """FAT/SAT steps whose printed result reads two ways: Evidence that proves nothing until
    a human confirms the value. Handwritten SAT entries are written in ``entry_language`` and
    read in the language of the form."""
    docs = {d.id: d for d in eq.documents if d.rev == 0}
    out: set[str] = set()
    for t in eq.tests:
        doc = docs.get(t.protocol)
        if doc is None or not isinstance(t.observed, NumberObs):
            continue
        printed = fmt_observation(t.observed, doc.entry_language or doc.language)
        if reads_two_ways(printed, doc.language):
            out.add(t.step)
    return frozenset(out)


def fmt_date(value: dt.date, lang: str) -> str:
    """``dd/mm/yyyy`` (id) or ``12-Mar-2026`` (en), design section 4."""
    return value.strftime("%d/%m/%Y") if lang == "id" else value.strftime("%d-%b-%Y")


def _with_unit(text: str, unit: str) -> str:
    return f"{text}%" if unit == "%" else f"{text} {unit}"


def fmt_spec(spec: Spec, lang: str) -> str:
    """An Acceptance Criterion: ``20–60 rpm``, ``≥ 100 kN``, ``≤ 0.8 µm``, ``SS 304``."""
    if isinstance(spec, RangeSpec):
        lo = None if spec.min is None else fmt_number(spec.min, lang)
        hi = None if spec.max is None else fmt_number(spec.max, lang)
        if lo is not None and hi is not None:
            text = lo if lo == hi else f"{lo}{EN_DASH}{hi}"
        else:
            text = f"≥ {lo}" if lo is not None else f"≤ {hi}"
        return _with_unit(text, spec.unit)
    if isinstance(spec, OneOfSpec):
        return (" atau " if lang == "id" else " or ").join(spec.allowed)
    if isinstance(spec, PresentSpec):
        return "Ada dan berfungsi" if lang == "id" else "Present and functional"
    raise RenderError(f"cannot render a {spec.type} spec")


def fmt_observation(obs: Observation, lang: str) -> str:
    if isinstance(obs, NumberObs):
        return _with_unit(fmt_number(obs.value, lang), obs.unit)
    if isinstance(obs, RangeObs):
        span = f"{fmt_number(obs.min, lang)}{EN_DASH}{fmt_number(obs.max, lang)}"
        return _with_unit(span, obs.unit)
    if isinstance(obs, TextObs):
        return obs.value
    if isinstance(obs, PresentObs):
        if lang == "id":
            return "Ada dan berfungsi" if obs.value else "Tidak ada"
        return "Present and functional" if obs.value else "Not present"
    raise RenderError(f"cannot render a {obs.type} observation")


def requirement_text(req: Requirement, spec: Spec, lang: str) -> str:
    """The requirement sentence with ``{min}``, ``{max}``, ``{allowed}`` filled from spec."""
    fields: dict[str, str] = {}
    if isinstance(spec, RangeSpec):
        fields = {
            k: fmt_number(v, lang)
            for k, v in (("min", spec.min), ("max", spec.max))
            if v is not None
        }
    elif isinstance(spec, OneOfSpec):
        fields = {"allowed": (" atau " if lang == "id" else " or ").join(spec.allowed)}
    try:
        return req.text.format(**fields)
    except KeyError as e:
        raise RenderError(f"{req.id}: text needs {e} but spec is {spec.type}") from None


# --- Documents ----------------------------------------------------------------------


def document(eq: Equipment, doc_id: str, rev: int) -> Document:
    for d in eq.documents:
        if d.id == doc_id and d.rev == rev:
            return d
    raise RenderError(f"{eq.tag}: no document {doc_id} rev {rev}")


def _require_filled(eq: Equipment) -> None:
    pending = eq.pending()
    if pending:
        raise RenderError(f"{eq.tag}: {len(pending)} pending value(s), e.g. {pending[0]}")


def _compile(
    template: str, data: dict, issued: dt.date, texts: Mapping[str, str], doc: Document
) -> Rendered:
    inputs = {"data": json.dumps(data, ensure_ascii=False)}
    common = {
        "root": TEMPLATES,
        "font_paths": [FONTS],
        "ignore_system_fonts": True,
        "sys_inputs": inputs,
    }
    path = TEMPLATES / template
    timestamp = int(dt.datetime.combine(issued, dt.time(), dt.UTC).timestamp())
    pdf, warnings = typst.compile_with_warnings(path, timestamp=timestamp, **common)
    if warnings:
        raise RenderError(f"{template}: Typst warnings: {warnings}")
    marks = {
        m["key"]: m for m in json.loads(typst.query(path, "<placed>", field="value", **common))
    }
    if set(marks) != set(texts):
        raise RenderError(f"{doc.id}: placed keys differ: {sorted(set(marks) ^ set(texts))}")
    placed = {
        k: Placed(
            marks[k]["page"], t, Box(*(marks[k][f] for f in "xywh")) if "w" in marks[k] else None
        )
        for k, t in texts.items()
    }
    return Rendered(doc_id=doc.id, rev=doc.rev, issued=issued, data=pdf, placed=placed)


def _signature(name: str | None, date: dt.date | None, lang: str) -> dict[str, str]:
    """A signature block row; an absent signatory leaves every cell empty."""
    if name is None:
        return {"name": "", "signature": "", "date": ""}
    signed = "Ditandatangani elektronik" if lang == "id" else "Signed electronically"
    return {"name": name, "signature": signed, "date": fmt_date(date, lang) if date else ""}


def render_urs(eq: Equipment, rev: int, t0: dt.date) -> Rendered:
    """URS (SKP) revision ``rev``. Rev 0 uses ``superseded_spec`` where one is set."""
    _require_filled(eq)
    doc = document(eq, f"URS-{eq.tag.replace('-', '')}", rev)
    if doc.layout == "prose":
        return _render_urs_prose(eq, doc, t0)
    lang = doc.language
    latest = max(d.rev for d in eq.documents if d.id == doc.id)
    people = {p.id: p.name for p in eq.people}
    issued = doc.issued_on.resolve(t0)

    texts: dict[str, str] = {}
    sections: dict[str, list[dict]] = {}
    for r in eq.requirements:
        spec = r.superseded_spec if (rev < latest and r.superseded_spec) else r.spec
        texts[r.id] = requirement_text(r, spec, lang)
        sections.setdefault(r.section, []).append(
            {"id": r.id, "critical": "Ya" if r.critical else "Tidak", "text": texts[r.id]}
        )

    history = [
        {
            "rev": d.rev,
            "date": fmt_date(d.issued_on.resolve(t0), lang),
            "note": d.change_note or "Terbitan pertama.",
        }
        for d in sorted(eq.documents, key=lambda d: d.rev)
        if d.id == doc.id and d.rev <= rev
    ]
    roles = (
        ("Disusun oleh", doc.prepared_by),
        ("Diperiksa oleh", doc.checked_by),
        ("Disetujui oleh", doc.approved_by),
    )
    data = {
        "doc_id": doc.id,
        "rev": rev,
        "title": "Spesifikasi Kebutuhan Pengguna (SKP)",
        "title_short": f"SKP {eq.tag}",
        "issued_on": fmt_date(issued, lang),
        "equipment": f"{eq.tag} {EN_DASH} {eq.name}",
        "purpose": (
            f"Dokumen ini menetapkan kebutuhan pengguna untuk {eq.tag}. Persyaratan dengan "
            "Kritis = Ya berdampak langsung pada mutu produk, keselamatan, atau integritas data."
        ),
        "sections": [{"title": t, "requirements": rs} for t, rs in sections.items()],
        "history": history,
        "signatures": [
            {"role": role, **_signature(people[pid] if pid else None, issued, lang)}
            for role, pid in roles
        ],
    }
    return _compile("urs.typ", data, issued, texts, doc)


def render_fat(eq: Equipment, doc_id: str, t0: dt.date) -> Rendered:
    """FAT protocol and report (one combined vendor document per protocol)."""
    _require_filled(eq)
    doc = document(eq, doc_id, 0)
    if doc.type != "fat":
        raise RenderError(f"{doc_id} is a {doc.type}, not a FAT")
    if doc.layout == "record":
        return _render_fat_record(eq, doc, t0)
    lang = doc.language
    protocol = next(p for p in eq.protocols if p.doc_id == doc_id)
    reqs = {r.id: r for r in eq.requirements}
    people = {p.id: p for p in eq.people}
    employers = {eq.site: "Customer (site)", eq.vendor.id: eq.vendor.name}
    issued = doc.issued_on.resolve(t0)
    approved = protocol.site_approved_on.resolve(t0) if protocol.site_approved_on else None
    executed = protocol.executed_on.resolve(t0)

    def row(role: str, pid: str | None, date: dt.date | None) -> dict[str, str]:
        person = people[pid] if pid else None
        company = employers[person.employer] if person else ""
        return {"role": role, "company": company, **_signature(person and person.name, date, lang)}

    texts: dict[str, str] = {}
    steps = []
    for t in eq.tests:
        if t.protocol != doc_id:
            continue
        if not t.description:
            raise RenderError(f"{t.step}: needs a description to be rendered")
        ac = fmt_spec(t.acceptance or reqs[t.requirement].spec, lang)
        obs = fmt_observation(t.observed, lang)
        texts[f"{t.step}.acceptance"], texts[f"{t.step}.observed"] = ac, obs
        steps.append(
            {
                "step": t.step,
                "description": t.description,
                "acceptance": ac,
                "observed": obs,
                "result": t.recorded_result.capitalize(),
            }
        )

    data = {
        "doc_id": doc.id,
        "rev": doc.rev,
        "title": doc.title,
        "vendor": eq.vendor.name,
        "issued_on": fmt_date(issued, lang),
        "equipment": f"{eq.tag} {EN_DASH} {eq.name}",
        "serial": eq.serial_no or "",
        "purpose": (
            f"This document defines and records the factory acceptance tests "
            f"({doc.title.lower()}) of the {eq.name.lower()} at the manufacturer's works, "
            "before shipment to the customer."
        ),
        "approvals": [
            row("Prepared by", doc.prepared_by, issued),
            row("Checked by", doc.checked_by, approved),
            row("Approved by", doc.approved_by, approved),
        ],
        "steps": steps,
        "deviations": "None recorded.",
        "execution": [
            row("Executed by", doc.executed_by, executed),
            row("Witnessed by", doc.witnessed_by, executed),
        ],
    }
    return _compile("fat.typ", data, issued, texts, doc)


def _render_urs_prose(eq: Equipment, doc: Document, t0: dt.date) -> Rendered:
    """A URS written as prose and unnumbered tables (design section 5, TP-202), with no
    requirement numbers. Per section: an opening sentence that states no requirement
    (``urs_intros``), the requirements without a ``table_label`` as one paragraph, and those
    with one as table rows with their criticality. Each requirement's span is placed."""
    lang, issued = doc.language, doc.issued_on.resolve(t0)
    people = _people(eq)
    texts: dict[str, str] = {}
    sections: dict[str, dict] = {}
    for r in eq.requirements:
        texts[r.id] = requirement_text(r, r.spec, lang)
        s = sections.setdefault(
            r.section,
            {
                "title": r.section,
                "intro": eq.urs_intros.get(r.section, ""),
                "prose": [],
                "rows": [],
            },
        )
        if r.table_label is None:
            s["prose"].append({"key": r.id, "text": texts[r.id]})
        else:
            s["rows"].append(
                {
                    "key": r.id,
                    "label": r.table_label,
                    "text": texts[r.id],
                    "critical": "Ya" if r.critical else "Tidak",
                }
            )
    roles = (
        ("Disusun oleh", doc.prepared_by),
        ("Diperiksa oleh", doc.checked_by),
        ("Disetujui oleh", doc.approved_by),
    )
    data = {
        "doc_id": doc.id,
        "rev": doc.rev,
        "title": "Spesifikasi Kebutuhan Pengguna",
        "issued_on": fmt_date(issued, lang),
        "equipment": f"{eq.tag} {EN_DASH} {eq.name}",
        "purpose": (
            f"Dokumen ini menguraikan kebutuhan {eq.site_name or 'site'} terhadap "
            f"{eq.name.lower()} {eq.tag}. Kebutuhan dalam tabel yang ditandai Kritis = Ya "
            "berdampak langsung pada mutu produk atau keselamatan."
        ),
        "sections": list(sections.values()),
        "note": doc.change_note or "Terbitan pertama.",
        "signatures": [
            {"role": role, **_signature(people[pid].name if pid else None, issued, lang)}
            for role, pid in roles
        ],
    }
    return _compile("urs_prose.typ", data, issued, texts, doc)


def _render_fat_record(eq: Equipment, doc: Document, t0: dt.date) -> Rendered:
    """A FAT from another vendor (design section 5, TP-202): as-built machine data, the
    customer's release of the procedure, one test record per step, a deviation statement,
    and a list of attachments none of which is bound in (``Document.attachments``)."""
    lang, issued = doc.language, doc.issued_on.resolve(t0)
    protocol = next(p for p in eq.protocols if p.doc_id == doc.id)
    reqs = {r.id: r for r in eq.requirements}
    people = _people(eq)
    employers = {eq.site: eq.site_name or "Customer", eq.vendor.id: eq.vendor.name}
    approved = protocol.site_approved_on.resolve(t0) if protocol.site_approved_on else None
    executed = protocol.executed_on.resolve(t0)
    texts: dict[str, str] = {}

    def put(key: str, text: str) -> str:
        texts[key] = text
        return text

    def row(role: str, pid: str | None, date: dt.date | None) -> dict[str, str]:
        person = people[pid] if pid else None
        company = employers[person.employer] if person else ""
        return {"role": role, "company": company, **_signature(person and person.name, date, lang)}

    as_built = [
        {"label": "Serial number", "value": eq.serial_no or ""},
        {"label": "Model", "value": eq.model or ""},
    ]
    for fact in eq.designs:
        if fact.doc_id != doc.id:
            continue
        key = design_field(eq, fact)
        assert key is not None and fact.label is not None
        value = put(key, fmt_design(fact.observed, lang))
        as_built.append({"label": fact.label, "value": value, "key": key})

    records = []
    for t in eq.tests:
        if t.protocol != doc.id:
            continue
        if not t.description:
            raise RenderError(f"{t.step}: needs a description to be rendered")
        ac = fmt_spec(t.acceptance or reqs[t.requirement].spec, lang)
        records.append(
            {
                "step": t.step,
                "description": t.description,
                "acceptance": put(f"{t.step}.acceptance", ac),
                "observed": put(f"{t.step}.observed", fmt_observation(t.observed, lang)),
                "result": put(f"{t.step}.result", t.recorded_result.upper()),
            }
        )
    attachments = [
        {"key": f"attachment.{n}", "text": put(f"attachment.{n}", f"Attachment {n}: {title}")}
        for n, title in enumerate(doc.attachments, 1)
    ]
    data = {
        "doc_id": doc.id,
        "rev": doc.rev,
        "title": doc.title,
        "vendor": eq.vendor.name,
        "issued_on": fmt_date(issued, lang),
        "customer": eq.site_name or "",
        "equipment": f"{eq.name}, customer tag {eq.tag}",
        "as_built": as_built,
        "release": [
            row("Issued", doc.prepared_by, issued),
            row("Reviewed (customer)", doc.checked_by, approved),
            row("Released for test (customer)", doc.approved_by, approved),
        ],
        "records": records,
        "deviations": put("deviations", "No deviations were raised during the test."),
        "attachments": attachments,
        "execution": [
            row("Tested by", doc.executed_by, executed),
            row("Witnessed by", doc.witnessed_by, executed),
        ],
    }
    return _compile("fat_record.typ", data, issued, texts, doc)


def render_sat(eq: Equipment, doc_id: str, t0: dt.date) -> Rendered:
    """SAT protocol and report: a printed English vendor form, filled in by hand at site.

    Handwritten entries use the document's ``entry_language`` for numbers and dates
    (``1.500 rpm``, scenario S7) and carry a bounding box. A :class:`Correction` draws the
    original value with the final one written over it (S1); the instrument table shows each
    calibration due date (S2); the serial number is the one written on this document (S3).
    """
    _require_filled(eq)
    doc = document(eq, doc_id, 0)
    if doc.type != "sat" or doc.entry_language is None:
        raise RenderError(f"{doc_id} is a {doc.type}, not a SAT")
    lang, hand = doc.language, doc.entry_language
    protocol = next(p for p in eq.protocols if p.doc_id == doc_id)
    reqs = {r.id: r for r in eq.requirements}
    people = {p.id: p for p in eq.people}
    instruments = {i.id: i for i in eq.instruments}
    employers = {eq.site: "Customer (site)", eq.vendor.id: eq.vendor.name}
    issued = doc.issued_on.resolve(t0)
    approved = protocol.site_approved_on.resolve(t0) if protocol.site_approved_on else None
    executed = protocol.executed_on.resolve(t0)
    texts: dict[str, str] = {}

    def put(key: str, text: str) -> str:
        texts[key] = text
        return text

    def row(role: str, key: str, pid: str | None, date: dt.date | None) -> dict[str, str]:
        empty = {"name": "", "company": "", "signature": "", "date": ""}
        if pid is None:
            return {"role": role, "key": key, **empty}
        person = people[pid]
        return {
            "role": role,
            "key": key,
            "name": put(f"{key}.name", person.name),
            "company": employers[person.employer],
            "signature": person.name.split()[-1],
            "date": put(f"{key}.date", fmt_date(date, hand)) if date else "",
        }

    steps: list[dict] = []
    used: list[str] = []
    for t in eq.tests:
        if t.protocol != doc_id:
            continue
        if not t.description:
            raise RenderError(f"{t.step}: needs a description to be rendered")
        used += [i for i in t.instruments if i not in used]
        ac = fmt_spec(t.acceptance or reqs[t.requirement].spec, lang)
        step = {
            "step": t.step,
            "description": t.description,
            "acceptance": put(f"{t.step}.acceptance", ac),
            "instruments": list(t.instruments),
            "observed": put(f"{t.step}.observed", fmt_observation(t.observed, hand)),
            "result": put(f"{t.step}.result", _result(t.recorded_result, hand)),
        }
        if t.instruments:
            put(f"{t.step}.instruments", " ".join(t.instruments))
        if isinstance(t.correction, Correction):
            original = fmt_observation(t.correction.original, hand)
            step["original"] = put(f"{t.step}.observed.original", original)
        steps.append(step)

    def instrument(i: str) -> dict[str, str]:
        cert = instruments[i].certificate
        due = fmt_date(cert.valid_until.resolve(t0), hand)
        key = f"instrument.{i}"
        return {
            "key": key,
            "id": put(f"{key}.id", i),
            "name": instruments[i].name,
            "serial": put(f"{key}.serial", instruments[i].serial_no),
            "certificate": put(f"{key}.certificate", cert.id),
            "due": put(f"{key}.due", due),
        }

    data = {
        "doc_id": doc.id,
        "rev": doc.rev,
        "vendor": eq.vendor.name,
        "issued_on": fmt_date(issued, lang),
        "equipment": f"{eq.tag} {EN_DASH} {eq.name}",
        "serial": put("serial", doc.serial_no or eq.serial_no or ""),
        "purpose": (
            "This document defines and records the site acceptance tests of the "
            f"{eq.name.lower()} after delivery and installation at the customer's site."
        ),
        "approvals": [
            row("Prepared by", "approval.prepared_by", doc.prepared_by, issued),
            row("Checked by", "approval.checked_by", doc.checked_by, approved),
            row("Approved by", "approval.approved_by", doc.approved_by, approved),
        ],
        "instruments": [instrument(i) for i in used],
        "steps": steps,
        "deviations": put("deviations", "Tidak ada" if hand == "id" else "None"),
        "execution": [
            row("Executed by", "execution.executed_by", doc.executed_by, executed),
            row("Witnessed by", "execution.witnessed_by", doc.witnessed_by, executed),
        ],
        "stamp": [eq.vendor.name.upper(), "SITE SERVICE", fmt_date(executed, "en").upper()],
    }
    return _compile("sat.typ", data, issued, texts, doc)


def _result(result: str, lang: str) -> str:
    if lang == "id":
        return "Lulus" if result == "pass" else "Gagal"
    return result.capitalize()


# --- Design documents and certificates ----------------------------------------------


def fmt_design(obs: Observation, lang: str) -> str:
    """A datasheet value: like an observation, but a feature is just ``Yes``."""
    if isinstance(obs, PresentObs):
        return (
            ("Ya" if lang == "id" else "Yes") if obs.value else ("Tidak" if lang == "id" else "No")
        )
    return fmt_observation(obs, lang)


def design_field(eq: Equipment, fact: DesignEvidence) -> str | None:
    """Key under which the renderer places a design fact; None if its document is not
    rendered. A datasheet row or functional-spec function is keyed by the requirement's
    parameter; a material certificate row by its position (``item-2.material``)."""
    doc = next((d for d in eq.documents if d.id == fact.doc_id), None)
    if doc is None:
        return None
    if doc.type in ("datasheet", "functional_spec"):
        return next(r.param for r in eq.requirements if r.id == fact.requirement)
    if doc.type == "fat":
        return "as_built." + next(r.param for r in eq.requirements if r.id == fact.requirement)
    if doc.type == "material_certificate":
        rows = [f for f in eq.designs if f.doc_id == fact.doc_id]
        return f"item-{next(i for i, f in enumerate(rows, 1) if f is fact)}.material"
    raise RenderError(f"{fact.doc_id}: a {doc.type} holds no design facts")


MATERIAL_NUMBERS = {"SS 304": "1.4301", "SS 316L": "1.4404"}
"""EN 10088 material numbers of the AISI grades used (304 = 1.4301, 316L = 1.4404)."""


def _people(eq: Equipment) -> dict[str, Person]:
    return {p.id: p for p in eq.people}


def render_datasheet(eq: Equipment, doc_id: str, t0: dt.date) -> Rendered:
    """Vendor technical datasheet: dense tables, one row per design fact, grouped by
    section. The serial number is the nameplate's (S3)."""
    _require_filled(eq)
    doc = document(eq, doc_id, 0)
    lang, issued = doc.language, doc.issued_on.resolve(t0)
    texts: dict[str, str] = {"serial": eq.serial_no or ""}
    sections: dict[str, list[dict]] = {}
    for fact in eq.designs:
        if fact.doc_id != doc_id:
            continue
        key = design_field(eq, fact)
        assert key is not None and fact.section is not None
        texts[key] = fmt_design(fact.observed, lang)
        sections.setdefault(fact.section, []).append(
            {"label": fact.label, "value": texts[key], "key": key}
        )
    ordered = [{"title": t, "rows": rows} for t, rows in sections.items()]
    half, count = sum(len(s["rows"]) for s in ordered) / 2, 0
    left = []
    for s in ordered:
        if count >= half:
            break
        left.append(s)
        count += len(s["rows"])
    prepared = _people(eq)[doc.prepared_by]
    data = {
        "doc_id": doc.id,
        "rev": doc.rev,
        "vendor": eq.vendor.name,
        "subtitle": f"{eq.model or ''} {eq.name.lower()}".strip(),
        "model": eq.model or "",
        "serial": texts["serial"],
        "customer": eq.site_name or "",
        "tag": eq.tag,
        "issued_on": fmt_date(issued, lang),
        "left": left,
        "right": ordered[len(left) :],
        "note": (
            f"Design values for machine serial no. {texts['serial']}, as built for the "
            "customer's order. Values marked max. are limits of the machine."
        ),
        "prepared": {
            "name": prepared.name,
            "signature": "Signed electronically",
            "date": fmt_date(issued, lang),
        },
    }
    return _compile("datasheet.typ", data, issued, texts, doc)


def render_material_certificate(eq: Equipment, doc_id: str, t0: dt.date) -> Rendered:
    """3.1 inspection certificate (EN 10204): one row per product-contact part (S6)."""
    _require_filled(eq)
    doc = document(eq, doc_id, 0)
    lang, issued = doc.language, doc.issued_on.resolve(t0)
    texts: dict[str, str] = {"serial": eq.serial_no or ""}
    items = []
    for fact in eq.designs:
        if fact.doc_id != doc_id:
            continue
        key = design_field(eq, fact)
        assert key is not None and isinstance(fact.observed, TextObs) and fact.label
        grade = fact.observed.value
        if grade not in MATERIAL_NUMBERS:
            raise RenderError(f"{doc_id}: no material number for {grade!r}")
        texts[key] = grade
        heat = zlib.crc32(f"{doc_id} {fact.label}".encode()) % 900000 + 100000
        items.append(
            {
                "pos": str(len(items) + 1),
                "part": fact.label,
                "material": grade,
                "key": key,
                "number": MATERIAL_NUMBERS[grade],
                "heat": f"H{heat}",
            }
        )
    inspector = _people(eq)[doc.prepared_by]
    data = {
        "doc_id": doc.id,
        "rev": doc.rev,
        "vendor": eq.vendor.name,
        "customer": eq.site_name or "",
        "equipment": f"{eq.model or eq.name}, customer tag {eq.tag}",
        "serial": texts["serial"],
        "issued_on": fmt_date(issued, lang),
        "items": items,
        "declaration": (
            "We hereby certify that the parts listed above are made of the material grades "
            "stated, verified against the mill certificates of the heats listed."
        ),
        "inspector": inspector.name,
        "signature": inspector.name.split()[-1],
        "stamp": [eq.vendor.name.upper(), "QUALITY INSPECTION", fmt_date(issued, "en").upper()],
    }
    return _compile("mtc.typ", data, issued, texts, doc)


def render_calibration_certificate(eq: Equipment, doc_id: str, t0: dt.date) -> Rendered:
    """Calibration certificate of a measuring instrument (S2: ``valid_until``), issued by a
    calibration lab or, for the press's own sensors, by the vendor. A system calibrated as one
    item lists each measuring channel."""
    _require_filled(eq)
    doc = document(eq, doc_id, 0)
    lang, issued = doc.language, doc.issued_on.resolve(t0)
    instrument = next(i for i in eq.instruments if i.certificate.id == doc_id)
    cert = instrument.certificate
    if cert.lab is None or cert.results is None:
        raise RenderError(f"{doc_id}: certificate needs a lab and results")
    by_vendor = cert.lab == eq.vendor.id
    issuer = eq.vendor.name if by_vendor else next(o.name for o in eq.labs if o.id == cert.lab)
    people = _people(eq)
    texts = {
        "instrument": instrument.id,
        "serial": instrument.serial_no,
        "calibrated_on": fmt_date(cert.calibrated_on.resolve(t0), lang),
        "valid_until": fmt_date(cert.valid_until.resolve(t0), lang),
    }
    unit = cert.results.unit

    def num(value: float) -> str:
        return fmt_number(round(value, 6), lang)

    channels = any(p.channel for p in cert.results.points)
    results = [
        ([p.channel or ""] if channels else [])
        + [
            num(p.nominal),
            num(p.reading),
            ("+" if p.reading > p.nominal else "") + num(p.reading - p.nominal),
            f"± {num(p.uncertainty)}",
        ]
        for p in cert.results.points
    ]
    signatures = [
        {"role": role, "name": people[pid].name, "signature": people[pid].name.split()[-1]}
        for role, pid in (("Calibrated by", doc.prepared_by), ("Approved by", doc.approved_by))
        if pid
    ]
    data = {
        "doc_id": doc.id,
        "rev": doc.rev,
        "lab": issuer,
        "customer": eq.site_name or "",
        "instrument": instrument.name,
        "asset": texts["instrument"],
        "serial": texts["serial"],
        "calibrated_on": texts["calibrated_on"],
        "valid_until": texts["valid_until"],
        "issued_on": fmt_date(issued, lang),
        "method": (
            "Comparison with the manufacturer's working reference standard, traceable to "
            "national standards, at the points below."
            if by_vendor
            else "Comparison with the laboratory's reference standard at the points below."
        ),
        "header": (["Channel"] if channels else [])
        + [
            f"Nominal ({unit})",
            f"Reading ({unit})",
            f"Error ({unit})",
            f"U, k = 2 ({unit})",
        ],
        "results": results,
        "statement": (
            "The expanded uncertainty U is the standard uncertainty multiplied by a coverage "
            "factor k = 2. The results relate only to the instrument calibrated."
        ),
        "signatures": signatures,
        "stamp": [issuer.upper(), "CALIBRATED", fmt_date(issued, "en").upper()],
    }
    return _compile("calibration.typ", data, issued, texts, doc)


def render_dq(eq: Equipment, doc_id: str, t0: dt.date) -> Rendered:
    """Design qualification report: every requirement of the reviewed URS revision against
    the reviewed datasheet. Clean: a design fact that misses the URS is an open item."""
    _require_filled(eq)
    doc = document(eq, doc_id, 0)
    lang, issued = doc.language, doc.issued_on.resolve(t0)
    types = {d.id: d.type for d in eq.documents}
    urs = next((r for r in doc.reviews if types.get(r.doc) == "urs"), None)
    ds = next((r for r in doc.reviews if types.get(r.doc) == "datasheet"), None)
    if urs is None or ds is None:
        raise RenderError(f"{doc_id}: a DQ reviews one URS and one datasheet")
    latest = max(d.rev for d in eq.documents if d.id == urs.doc)
    facts = {f.requirement: f for f in eq.designs if f.doc_id == ds.doc}
    rows, open_items = [], []
    for r in eq.requirements:
        spec = r.superseded_spec if (urs.rev < latest and r.superseded_spec) else r.spec
        fact = facts.get(r.id)
        design = f"{fact.label}: {fmt_design(fact.observed, 'en')}" if fact else EN_DASH
        if fact is None:
            result = "Diverifikasi saat IQ/OQ" if r.site_only else "Diverifikasi saat FAT/SAT"
        elif meets(spec, fact.observed):
            result = "Sesuai"
        else:
            open_items.append(
                f'{r.id}: {ds.doc} mencantumkan "{design}", sedangkan SKP mensyaratkan '
                f"{fmt_spec(spec, lang)}. Vendor diminta mengonfirmasi desain atau mengajukan "
                "perubahan; butir ini dilacak sampai ditutup."
            )
            result = f"Tidak sesuai (butir terbuka {len(open_items)})"
        rows.append(
            {
                "id": r.id,
                "text": requirement_text(r, spec, lang),
                "design": design,
                "result": result,
            }
        )
    people = _people(eq)
    roles = (
        ("Disusun oleh", doc.prepared_by),
        ("Diperiksa oleh", doc.checked_by),
        ("Disetujui oleh", doc.approved_by),
    )
    conclusion = f"Desain {eq.tag} memenuhi SKP rev {urs.rev}" + (
        f", kecuali {len(open_items)} butir terbuka di bagian 4. Desain diterima dengan "
        "butir terbuka tersebut."
        if open_items
        else ". Desain diterima."
    )
    data = {
        "doc_id": doc.id,
        "rev": doc.rev,
        "title": "Laporan Kualifikasi Desain (DQ)",
        "title_short": f"DQ {eq.tag}",
        "issued_on": fmt_date(issued, lang),
        "equipment": f"{eq.tag} {EN_DASH} {eq.name}",
        "purpose": (
            f"Laporan ini mencatat tinjauan desain {eq.tag} dari vendor terhadap SKP: setiap "
            "persyaratan dibandingkan dengan data desain, atau ditandai untuk diverifikasi "
            "pada tahap kualifikasi berikutnya."
        ),
        "reviewed": [
            {"doc": urs.doc, "rev": str(urs.rev), "title": "Spesifikasi Kebutuhan Pengguna (SKP)"},
            {"doc": ds.doc, "rev": str(ds.rev), "title": f"Technical Datasheet ({eq.vendor.name})"},
        ],
        "datasheet": ds.doc,
        "rows": rows,
        "open": open_items,
        "conclusion": conclusion,
        "signatures": [
            {"role": role, **_signature(people[pid].name if pid else None, issued, lang)}
            for role, pid in roles
        ],
    }
    return _compile("dq.typ", data, issued, {}, doc)


def render_functional_spec(eq: Equipment, doc_id: str, t0: dt.date) -> Rendered:
    """Vendor functional design specification: one numbered function per design fact,
    grouped by section, with no URS numbers (mapping is the Traceability AI's job). Clean."""
    _require_filled(eq)
    doc = document(eq, doc_id, 0)
    lang, issued = doc.language, doc.issued_on.resolve(t0)
    texts: dict[str, str] = {}
    sections: dict[str, list[dict]] = {}
    for fact in eq.designs:
        if fact.doc_id != doc_id:
            continue
        key = design_field(eq, fact)
        assert key is not None and fact.section and fact.label and fact.description
        texts[key] = fact.label
        sections.setdefault(fact.section, []).append(
            {"label": fact.label, "key": key, "description": fact.description}
        )
    people = _people(eq)
    roles = (
        ("Prepared by", doc.prepared_by),
        ("Checked by", doc.checked_by),
        ("Approved by", doc.approved_by),
    )
    employers = {eq.site: "Customer (site)", eq.vendor.id: eq.vendor.name}
    data = {
        "doc_id": doc.id,
        "rev": doc.rev,
        "vendor": eq.vendor.name,
        "issued_on": fmt_date(issued, lang),
        "equipment": f"{eq.tag} {EN_DASH} {eq.name}",
        "model": eq.model or "",
        "serial": eq.serial_no or "",
        "customer": eq.site_name or "",
        "purpose": (
            f"This document describes the functions, interlocks and data handling of the "
            f"{eq.model or ''} {eq.name.lower()} control system as designed for the customer's "
            "order. It is the basis of the control-system factory acceptance test."
        ).replace("  ", " "),
        "overview": (
            "The press is controlled by a PLC with a touch-screen HMI on the operator panel. "
            "Turret and feeder have separate frequency-controlled drives. The PLC processes "
            "the compression force signals for weight control, rejection and overload "
            "protection; safety functions act through a separate safety relay."
        ),
        "modes": [
            {
                "name": "Setup",
                "text": "Turret jogged with hold-to-run buttons; production "
                "functions and the reject gate are disabled.",
            },
            {
                "name": "Production",
                "text": "Recipe-controlled operation with weight control, "
                "rejection and batch counters active.",
            },
            {
                "name": "Cleaning",
                "text": "All drives locked; product-contact parts can be removed for cleaning.",
            },
        ],
        "sections": [{"title": t, "functions": fs} for t, fs in sections.items()],
        "approvals": [
            {
                "role": role,
                "company": employers[people[pid].employer] if pid else "",
                **_signature(people[pid].name if pid else None, issued, lang),
            }
            for role, pid in roles
        ],
    }
    return _compile("fds.typ", data, issued, texts, doc)


RA_SHEET = "Penilaian Risiko"
RA_COLUMNS = (
    ("No", 5),
    ("No. SKP", 15),
    ("Persyaratan", 48),
    ("Mode kegagalan", 34),
    ("Dampak", 40),
    ("S", 5),
    ("O", 5),
    ("D", 5),
    ("RPN", 7),
    ("Aspek kritis", 12),
    ("Pengendalian dan verifikasi", 40),
)
RA_SCORES = ("severity", "occurrence", "detection", "rpn", "critical")
"""Placed cells of each FMEA row: ``<requirement id>.<name>``."""


def render_risk_assessment(eq: Equipment, doc_id: str, t0: dt.date) -> Rendered:
    """Site risk assessment as a spreadsheet: a short FMEA, one row per requirement of the
    reviewed URS revision, marking the Critical Aspects (severity >= ``critical_from``).
    Values, not formulas, so a reader needs no cached results. Clean."""
    _require_filled(eq)
    doc = document(eq, doc_id, 0)
    ra = eq.risk_assessment
    if ra is None or ra.doc_id != doc_id:
        raise RenderError(f"{doc_id}: no risk_assessment with this doc_id")
    urs = doc.reviews[0] if doc.reviews else None
    if urs is None:
        raise RenderError(f"{doc_id}: a risk assessment reviews one URS revision")
    lang, issued = doc.language, doc.issued_on.resolve(t0)
    latest = max(d.rev for d in eq.documents if d.id == urs.doc)
    people = _people(eq)

    wb = Workbook()
    ws = wb.active
    assert isinstance(ws, Worksheet)
    ws.title = RA_SHEET
    bold, thin = Font(bold=True), Side(style="thin")
    grid = Border(left=thin, right=thin, top=thin, bottom=thin)
    wrap = Alignment(wrap_text=True, vertical="top")
    ws["A1"] = f"Penilaian Risiko (FMEA) {eq.tag} {EN_DASH} {eq.name}"
    ws["A1"].font = Font(bold=True, size=13)
    header = (
        ("No. dokumen", doc.id),
        ("Revisi", str(doc.rev)),
        ("Tanggal terbit", fmt_date(issued, lang)),
        ("Peralatan", f"{eq.tag} {EN_DASH} {eq.name}"),
        ("Dokumen acuan", f"{urs.doc} rev {urs.rev} (SKP)"),
    )
    for i, (label, value) in enumerate(header, 3):
        ws.cell(i, 1, label).font = bold
        ws.cell(i, 3, value)
        ws.merge_cells(start_row=i, start_column=1, end_row=i, end_column=2)
    top = 3 + len(header) + 1
    for col, (title, width) in enumerate(RA_COLUMNS, 1):
        c = ws.cell(top, col, title)
        c.font, c.border, c.alignment = bold, grid, wrap
        c.fill = PatternFill("solid", fgColor="D9D9D9")
        ws.column_dimensions[c.column_letter].width = width
    ws.freeze_panes = ws.cell(top + 1, 1).coordinate

    texts: dict[str, str] = {}
    cells: dict[str, str] = {}
    rows = {row.requirement: row for row in ra.rows}
    for n, r in enumerate(eq.requirements, 1):
        row = rows[r.id]
        spec = r.superseded_spec if (urs.rev < latest and r.superseded_spec) else r.spec
        critical = "Ya" if ra.critical(row) else "Tidak"
        values = (
            n,
            r.id,
            requirement_text(r, spec, lang),
            row.failure_mode,
            row.effect,
            row.severity,
            row.occurrence,
            row.detection,
            row.rpn,
            critical,
            ra.controls[r.scope],
        )
        y = top + n
        for col, value in enumerate(values, 1):
            c = ws.cell(y, col, value)
            c.border, c.alignment = grid, wrap
        scores = dict(
            zip(
                RA_SCORES,
                (row.severity, row.occurrence, row.detection, row.rpn, critical),
                strict=True,
            )
        )
        for col, name in enumerate(RA_SCORES, 6):
            key = f"{r.id}.{name}"
            texts[key] = str(scores[name])
            cells[key] = ws.cell(y, col).coordinate

    y = top + len(eq.requirements) + 2
    legend = (
        "S = keparahan (severity), O = kemungkinan terjadi (occurrence), D = deteksi "
        "(detection; 1 = hampir pasti terdeteksi, 5 = sulit terdeteksi). Skala 1"
        f"{EN_DASH}5. RPN = S {TIMES} O {TIMES} D.",
        f"Aspek kritis = Ya bila S ≥ {ra.critical_from}: kegagalan berdampak langsung pada "
        "mutu produk, keselamatan, atau integritas data.",
        "RPN menentukan prioritas pengujian: makin tinggi RPN, makin awal dan makin ketat "
        "pengujiannya di protokol kualifikasi.",
    )
    for i, line in enumerate(legend):
        ws.cell(y + i, 1, line)
    y += len(legend) + 1
    for col, title in enumerate(("Peran", "", "Nama", "Tanggal"), 1):
        if title:
            ws.cell(y, col, title).font = bold
    for i, (role, pid) in enumerate(
        (
            ("Disusun oleh", doc.prepared_by),
            ("Diperiksa oleh", doc.checked_by),
            ("Disetujui oleh", doc.approved_by),
        ),
        1,
    ):
        ws.cell(y + i, 1, role)
        ws.cell(y + i, 3, people[pid].name if pid else "")
        ws.cell(y + i, 4, fmt_date(issued, lang) if pid else "")

    author = people[doc.prepared_by].name
    wb.properties.creator = wb.properties.lastModifiedBy = author
    wb.properties.title = f"{doc.id} rev {doc.rev}"
    buf = io.BytesIO()
    wb.save(buf)
    placed = {k: Placed(1, t, sheet=RA_SHEET, cell=cells[k]) for k, t in texts.items()}
    return Rendered(
        doc_id=doc.id,
        rev=doc.rev,
        issued=issued,
        data=_fixed_dates(buf.getvalue(), issued),
        placed=placed,
        format="xlsx",
    )


_W3CDTF = re.compile(rb"(<dcterms:(created|modified) [^>]*>)[^<]*(</dcterms:)")


def _fixed_dates(xlsx: bytes, issued: dt.date) -> bytes:
    """Repack an XLSX with every zip entry and document-property date set to ``issued``:
    openpyxl writes the current time to both, so the bytes would differ per run."""
    stamp = issued.strftime("%Y-%m-%dT00:00:00Z").encode()
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(xlsx)) as src, zipfile.ZipFile(out, "w") as dst:
        for info in src.infolist():
            data = src.read(info.filename)
            if info.filename == "docProps/core.xml":
                data = _W3CDTF.sub(rb"\g<1>" + stamp + rb"\g<3>", data)
            entry = zipfile.ZipInfo(info.filename, date_time=(*issued.timetuple()[:3], 0, 0, 0))
            dst.writestr(entry, data, compress_type=zipfile.ZIP_DEFLATED)
    return out.getvalue()


# --- Governing documents (VMP, qualification SOP) -------------------------------------

DOC_TYPES_ID = {
    "urs": "Spesifikasi Kebutuhan Pengguna (SKP)",
    "risk_assessment": "Penilaian risiko (FMEA)",
    "datasheet": "Lembar data teknis vendor",
    "functional_spec": "Spesifikasi desain fungsional (FDS)",
    "dq_report": "Laporan Kualifikasi Desain (DQ)",
    "material_certificate": "Sertifikat material 3.1 bagian kontak produk",
    "calibration_certificate": "Sertifikat kalibrasi",
    "fat": "Protokol dan laporan FAT",
    "sat": "Protokol dan laporan SAT",
    "iq_protocol": "Protokol IQ",
    "oq_protocol": "Protokol OQ",
}
"""Required-document types as the VMP names them (Indonesian)."""

STAGES_ID = {"design": "Desain", "FAT": "FAT", "SAT": "SAT", "IQ": "IQ", "OQ": "OQ"}


def _governing(eq: Equipment, doc_id: str) -> Document:
    """A governing document is rendered in one revision: the one in force at T0."""
    docs = [d for d in eq.documents if d.id == doc_id]
    if len(docs) != 1:
        raise RenderError(f"{eq.tag}: {doc_id} needs exactly one revision")
    return docs[0]


def _site_frame(eq: Equipment, doc: Document, t0: dt.date) -> dict:
    """Header, revision entry and approval block shared by the governing documents."""
    lang, issued = doc.language, doc.issued_on.resolve(t0)
    people = _people(eq)
    roles = (
        ("Disusun oleh", doc.prepared_by),
        ("Diperiksa oleh", doc.checked_by),
        ("Disetujui oleh", doc.approved_by),
    )
    return {
        "doc_id": doc.id,
        "rev": doc.rev,
        "issued_on": fmt_date(issued, lang),
        "site": eq.site_name or "",
        "history": [
            {
                "rev": str(doc.rev),
                "date": fmt_date(issued, lang),
                "note": doc.change_note or "Terbitan pertama.",
            }
        ],
        "signatures": [
            {"role": role, **_signature(people[pid].name if pid else None, issued, lang)}
            for role, pid in roles
        ],
    }


def _required_label(eq: Equipment, req_type: str, doc_id: str) -> str:
    label = DOC_TYPES_ID[req_type]
    if req_type == "calibration_certificate":
        inst = next(i for i in eq.instruments if i.certificate.id == doc_id)
        return f"{label}: {inst.name} ({inst.id})"
    title = next((d.title for d in eq.documents if d.id == doc_id and d.title), "")
    return f"{label} ({title})" if title else label


def render_vmp(eq: Equipment, doc_id: str, t0: dt.date) -> Rendered:
    """Validation Master Plan (Indonesian, born-digital): qualification stages and, in its
    annex, the documents required for the Equipment (``required_documents``), so the system
    learns that list from the corpus. It prints no status: finding what is missing is the
    reader's job."""
    doc = _governing(eq, doc_id)
    issued = doc.issued_on.resolve(t0)
    sop = next((d.id for d in eq.documents if d.type == "sop"), None)
    texts: dict[str, str] = {}
    rows = []
    for r in eq.required_documents:
        key = f"required.{r.id}"
        texts[key] = r.id
        cells = [r.id, _required_label(eq, r.type, r.id), STAGES_ID[r.stage]]
        rows.append({"key": key, "cells": cells})
    stages = (
        ("Desain", "SKP, penilaian risiko, data desain vendor, dan Kualifikasi Desain (DQ)."),
        ("FAT", "Uji penerimaan di pabrik vendor dengan protokol vendor."),
        ("SAT", "Uji penerimaan di site setelah instalasi."),
        ("IQ", "Kualifikasi instalasi dengan protokol yang disusun site."),
        ("OQ", "Kualifikasi operasional dengan protokol yang disusun site."),
    )
    sections = [
        {
            "title": "Tujuan",
            "paragraphs": [
                "Rencana Induk Validasi ini menetapkan pendekatan kualifikasi peralatan di "
                f"{eq.site_name or 'site'}: tahapan kualifikasi, tanggung jawab, dan dokumen "
                "yang dipersyaratkan untuk setiap peralatan."
            ],
        },
        {
            "title": "Ruang lingkup",
            "paragraphs": [
                "Peralatan produksi sediaan padat oral beserta sistem kendalinya. Kualifikasi "
                "kinerja (PQ) dilaksanakan bersama validasi proses dan diatur dalam protokol "
                "validasi proses, di luar paket dokumen kualifikasi peralatan."
            ],
        },
        {
            "title": "Tahapan kualifikasi",
            "table": {
                "columns": [1, 4],
                "header": ["Tahap", "Kegiatan"],
                "rows": [{"cells": list(s)} for s in stages],
            },
        },
        {
            "title": "Tanggung jawab dan dokumentasi",
            "paragraphs": [
                "Penandatangan, pemisahan tugas, koreksi catatan, dan Saksi diatur dalam "
                + (f"Protap {sop}." if sop else "Protap kualifikasi peralatan.")
            ],
        },
        {
            "title": "Penomoran dokumen",
            "paragraphs": [
                "Dokumen kualifikasi site diberi nomor jenis dokumen diikuti tag peralatan "
                f"tanpa tanda hubung, misalnya SKP URS-{eq.tag.replace('-', '')}. Dokumen "
                "vendor dan sertifikat memakai nomor penerbitnya."
            ],
        },
        {
            "title": f"Lampiran 1. Dokumen yang dipersyaratkan: {eq.tag} {EN_DASH} {eq.name}",
            "paragraphs": [
                f"Peralatan baru {eq.tag} tidak dirilis untuk penggunaan produksi sebelum "
                "seluruh dokumen berikut tersedia dan disetujui."
            ],
            "table": {
                "columns": [2, 4, 1],
                "header": ["No. dokumen", "Jenis dokumen", "Tahap"],
                "rows": rows,
            },
        },
    ]
    data = {
        **_site_frame(eq, doc, t0),
        "title": "Rencana Induk Validasi (Validation Master Plan)",
        "title_short": "Rencana Induk Validasi",
        "sections": sections,
    }
    return _compile("governing.typ", data, issued, texts, doc)


WITNESS_RULES = {
    "critical_aspects": (
        "Langkah Uji yang memverifikasi Aspek Kritis (persyaratan dengan Kritis = Ya dalam "
        "SKP dan penilaian risiko) wajib disaksikan oleh Saksi, yang membubuhkan paraf dan "
        "tanggal pada hasil. Langkah Uji lain tidak memerlukan Saksi."
    ),
    "all": (
        "Setiap Langkah Uji wajib disaksikan oleh Saksi, yang membubuhkan paraf dan tanggal "
        "pada hasil."
    ),
}
"""SOP text per ``SiteRules.witness`` (design section 12, **[D]**)."""

PROTOCOL_RULES = {
    "template": (
        "Protokol IQ/OQ disusun dari templat protokol standar site untuk setiap peralatan; "
        "protokol tidak disalin dari protokol peralatan lain."
    ),
    "copied": (
        "Protokol IQ/OQ boleh disusun dengan menyalin protokol peralatan sejenis; setiap tag, "
        "nilai, dan rujukan peralatan asal diganti dan diperiksa sebelum persetujuan."
    ),
}
"""SOP text per ``SiteRules.protocols`` (design section 12, **[D]**)."""


def render_sop(eq: Equipment, doc_id: str, t0: dt.date) -> Rendered:
    """Qualification SOP (Protap, Indonesian, born-digital): signatories, segregation of
    duties, GDP corrections, which Test Steps need a Witness, and how protocols are written.
    The last two follow ``Equipment.site_rules``."""
    doc = _governing(eq, doc_id)
    rules = eq.site_rules
    if rules is None:
        raise RenderError(f"{doc_id}: an SOP needs site_rules")
    issued = doc.issued_on.resolve(t0)
    texts = {
        "signatories": (
            "Protokol FAT/SAT vendor diperiksa dan disetujui site sebelum dieksekusi. Setiap "
            "tanda tangan disertai nama dan tanggal."
        ),
        "segregation": (
            "Dalam satu dokumen, penyusun tidak boleh menyetujui dokumen yang disusunnya, "
            "pemeriksa dan penyetuju adalah dua orang yang berbeda, dan pelaksana tidak boleh "
            "sekaligus menjadi Saksi pada Langkah Uji yang sama."
        ),
        "gdp": (
            "Koreksi pada catatan dibuat dengan mencoret nilai lama dengan satu garis sehingga "
            "tetap terbaca, menulis nilai baru di dekatnya, serta membubuhkan paraf, tanggal, "
            "dan alasan koreksi. Nilai tidak boleh ditimpa, dihapus, atau ditutup dengan "
            "cairan koreksi (CPOB 10.8; PIC/S PI 041-1 §8.7)."
        ),
        "witness": WITNESS_RULES[rules.witness],
        "protocols": PROTOCOL_RULES[rules.protocols],
    }
    signers = (
        (
            "Dokumen site (SKP, penilaian risiko, DQ, protokol IQ/OQ)",
            "Qualification Engineer",
            "Qualification Supervisor",
            "QA Approver",
        ),
        ("Protokol FAT/SAT vendor", "Vendor", "Qualification Supervisor", "QA Approver"),
    )

    def rule(title: str, key: str) -> dict:
        return {"title": title, "paragraphs": [{"key": key, "text": texts[key]}]}

    sections = [
        {
            "title": "Tujuan",
            "paragraphs": [
                "Prosedur ini menetapkan cara menyusun, menandatangani, mengeksekusi, dan "
                "mengoreksi dokumen kualifikasi peralatan."
            ],
        },
        {
            "title": "Ruang lingkup",
            "paragraphs": [
                "Dokumen kualifikasi site (SKP, penilaian risiko, DQ, protokol dan laporan "
                "IQ/OQ) serta protokol FAT/SAT vendor yang digunakan sebagai Bukti. Dokumen "
                "vendor lain (lembar data, FDS, sertifikat) ditandatangani sesuai sistem mutu "
                "penerbitnya."
            ],
        },
        {
            **rule("Penandatangan", "signatories"),
            "table": {
                "columns": [3, 2, 2, 2],
                "header": ["Dokumen", "Disusun oleh", "Diperiksa oleh", "Disetujui oleh"],
                "rows": [{"cells": list(s)} for s in signers],
            },
        },
        rule("Pemisahan tugas", "segregation"),
        rule("Koreksi catatan (GDP)", "gdp"),
        rule("Saksi (Witness)", "witness"),
        rule("Penyusunan protokol", "protocols"),
    ]
    data = {
        **_site_frame(eq, doc, t0),
        "title": "Prosedur Tetap: Kualifikasi Peralatan",
        "title_short": "Protap Kualifikasi Peralatan",
        "sections": sections,
    }
    return _compile("governing.typ", data, issued, texts, doc)


ASSESSMENT_AREAS = {
    "mechanical": (
        "Mekanik (mechanical)",
        "Desain dan fabrikasi mekanik, material bagian kontak produk, uji fungsi mekanik.",
    ),
    "control": (
        "Sistem kendali dan perangkat lunak (control system/software)",
        "PLC, HMI, perangkat lunak kendali dan uji fungsi kendali.",
    ),
    "data_integrity": (
        "Integritas data (data integrity)",
        "Hak akses, audit trail, log alarm, cadangan data dan sinkronisasi waktu.",
    ),
    "documentation": (
        "Dokumentasi (documentation)",
        "Pengendalian dokumen, sertifikat material dan kalibrasi, protokol FAT/SAT.",
    ),
}
"""Areas every Vendor Assessment rates, keyed by ``VendorAssessment.scope`` (Indonesian,
with the English area name the site's vendor questionnaire uses)."""


def render_vendor_assessment(eq: Equipment, doc_id: str, t0: dt.date) -> Rendered:
    """Vendor Assessment (Indonesian, born-digital): the site's evaluation of the vendor
    and the areas whose results it may rely on (CPOB Ch. 12; Coverage condition 1, design
    section 6). Every area is printed with ``Ya`` or ``Tidak``, so a limited scope is as
    citable as a full one."""
    doc = _governing(eq, doc_id)
    assessment = eq.vendor.assessment
    if assessment is None:
        raise RenderError(f"{doc_id}: a Vendor Assessment needs vendor.assessment")
    unknown = sorted(assessment.scope - set(ASSESSMENT_AREAS))
    if unknown:
        raise RenderError(f"{doc_id}: no assessment area for scope {unknown}")
    issued = doc.issued_on.resolve(t0)
    texts: dict[str, str] = {}
    rows = []
    for key, (label, activities) in ASSESSMENT_AREAS.items():
        texts[f"scope.{key}"] = label
        relied = "Ya" if key in assessment.scope else "Tidak"
        rows.append({"key": f"scope.{key}", "cells": [label, relied, activities]})
    limited = set(ASSESSMENT_AREAS) - assessment.scope
    conclusion = (
        "Pemasok disetujui untuk seluruh area di atas."
        if not limited
        else "Pemasok disetujui dengan ruang lingkup terbatas: area dengan hasil Tidak belum "
        "dinilai, sehingga hasil uji pemasok untuk area tersebut tidak dapat digunakan "
        "sebagai Bukti dan diuji oleh site."
    )
    machine = f"{eq.tag} {EN_DASH} {eq.name}" + (f", model {eq.model}" if eq.model else "")
    sections = [
        {
            "title": "Tujuan",
            "paragraphs": [
                f"Laporan ini mencatat penilaian site terhadap pemasok {eq.vendor.name} "
                "dan menetapkan area kegiatan pemasok yang hasilnya dapat diandalkan site "
                "dalam kualifikasi peralatan (CPOB Bab 12)."
            ],
        },
        {
            "title": "Pengadaan terkait",
            "paragraphs": [f"Peralatan {machine}."],
        },
        {
            "title": "Metode penilaian",
            "paragraphs": [
                "Kuesioner pemasok, tinjauan sistem mutu pemasok, dan audit di lokasi pemasok "
                "oleh Qualification Supervisor dan QA."
            ],
        },
        {
            "title": "Ruang lingkup yang dinilai",
            "paragraphs": [
                "Hasil uji pemasok (FAT/SAT) dapat digunakan sebagai Bukti kualifikasi hanya "
                "untuk area dengan hasil Ya."
            ],
            "table": {
                "columns": [3, 1, 4],
                "header": ["Area", "Dapat diandalkan", "Kegiatan yang dinilai"],
                "rows": rows,
            },
        },
        {"title": "Kesimpulan", "paragraphs": [conclusion]},
    ]
    data = {
        **_site_frame(eq, doc, t0),
        "title": "Laporan Penilaian Pemasok (Vendor Assessment)",
        "title_short": "Penilaian Pemasok",
        "sections": sections,
    }
    return _compile("governing.typ", data, issued, texts, doc)


RENDERERS = {
    "fat": render_fat,
    "sat": render_sat,
    "datasheet": render_datasheet,
    "functional_spec": render_functional_spec,
    "material_certificate": render_material_certificate,
    "calibration_certificate": render_calibration_certificate,
    "dq_report": render_dq,
    "risk_assessment": render_risk_assessment,
    "vmp": render_vmp,
    "sop": render_sop,
    "vendor_assessment": render_vendor_assessment,
}


def render_all(eq: Equipment, t0: dt.date) -> list[Rendered]:
    return [
        render_urs(eq, d.rev, t0) if d.type == "urs" else RENDERERS[d.type](eq, d.id, t0)
        for d in eq.documents
    ]


def main(argv: list[str]) -> int:
    from traceq_dataset.corpus import build_corpus, manifest
    from traceq_dataset.degrade import SEED
    from traceq_dataset.world import load

    parser = argparse.ArgumentParser(prog="traceq_dataset.render")
    parser.add_argument("world", type=Path, nargs="+")
    parser.add_argument("--t0", type=dt.date.fromisoformat, default=EVAL_T0)
    parser.add_argument("--seed", type=int, default=SEED, help="degrader seed for scans")
    parser.add_argument("--out", type=Path, default=Path("dist"))
    args = parser.parse_args(argv)

    root = args.out / f"t0-{args.t0.isoformat()}"
    corpora = [build_corpus(load(w), args.t0, args.seed) for w in args.world]
    for c in corpora:
        out = root / c.eq.tag
        out.mkdir(parents=True, exist_ok=True)
        for key, r in c.rendered.items():
            # A paper document is published only as its scan.
            data = c.published(key)
            note = f"scan, {c.scanned[key].level}" if key in c.scanned else r.format
            (out / r.filename).write_bytes(data)
            print(f"{out / r.filename}  ({len(data):,} bytes, {note}, {len(r.placed)} placed)")
    text = json.dumps(manifest(corpora), ensure_ascii=False, indent=2) + "\n"
    (root / "manifest.json").write_text(text, encoding="utf-8", newline="\n")
    print(root / "manifest.json")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
