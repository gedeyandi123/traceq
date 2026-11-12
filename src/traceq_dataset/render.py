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
answer key can locate them on the datasheet and the material certificate.

Usage::

    uv run python -m traceq_dataset.render world/tp201.yaml [--t0 YYYY-MM-DD] [--out dist]

writes ``dist/t0-<T0>/<tag>/*.pdf`` and the corpus ``manifest.json``.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import zlib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import typst

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

    ``box`` is set for handwritten entries: the OCR answer key needs where they are.
    """

    page: int
    text: str
    box: Box | None = None

    @property
    def handwritten(self) -> bool:
        return self.box is not None


@dataclass(frozen=True)
class Rendered:
    doc_id: str
    rev: int
    issued: dt.date
    """Issue date, also the PDF metadata date."""
    pdf: bytes
    placed: Mapping[str, Placed]
    """Keyed by requirement id (URS), ``<step>.acceptance`` / ``<step>.observed`` (FAT,
    SAT), a handwritten field (SAT, e.g. ``serial``, ``SAT-01.observed.original``), a design
    fact (:func:`design_field`) or a certificate field (``valid_until``)."""

    @property
    def filename(self) -> str:
        return f"{self.doc_id}_rev{self.rev}.pdf"


# --- Formatting ---------------------------------------------------------------------


def fmt_number(value: float, lang: str) -> str:
    """``120000`` → ``120.000`` (id) / ``120,000`` (en); ``0.8`` → ``0,8`` (id)."""
    text = f"{value:,.10g}"
    return text.translate(str.maketrans(",.", ".,")) if lang == "id" else text


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
    return Rendered(doc_id=doc.id, rev=doc.rev, issued=issued, pdf=pdf, placed=placed)


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
    rendered. A datasheet row is keyed by the requirement's parameter; a material
    certificate row by its position (``item-2.material``)."""
    doc = next((d for d in eq.documents if d.id == fact.doc_id), None)
    if doc is None:
        return None
    if doc.type == "datasheet":
        return next(r.param for r in eq.requirements if r.id == fact.requirement)
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
    """Calibration certificate of a site test instrument (S2: ``valid_until``)."""
    _require_filled(eq)
    doc = document(eq, doc_id, 0)
    lang, issued = doc.language, doc.issued_on.resolve(t0)
    instrument = next(i for i in eq.instruments if i.certificate.id == doc_id)
    cert = instrument.certificate
    if cert.lab is None or cert.results is None:
        raise RenderError(f"{doc_id}: certificate needs a lab and results")
    lab = next(o for o in eq.labs if o.id == cert.lab)
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

    results = [
        {
            "nominal": num(p.nominal),
            "reading": num(p.reading),
            "error": ("+" if p.reading > p.nominal else "") + num(p.reading - p.nominal),
            "uncertainty": f"± {num(p.uncertainty)}",
        }
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
        "lab": lab.name,
        "customer": eq.site_name or "",
        "instrument": instrument.name,
        "asset": texts["instrument"],
        "serial": texts["serial"],
        "calibrated_on": texts["calibrated_on"],
        "valid_until": texts["valid_until"],
        "issued_on": fmt_date(issued, lang),
        "method": "Comparison with the laboratory's reference standard at the points below.",
        "header": [
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
        "stamp": [lab.name.upper(), "CALIBRATED", fmt_date(issued, "en").upper()],
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


RENDERERS = {
    "fat": render_fat,
    "sat": render_sat,
    "datasheet": render_datasheet,
    "material_certificate": render_material_certificate,
    "calibration_certificate": render_calibration_certificate,
    "dq_report": render_dq,
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
            pdf = c.published(key)
            note = f"scan, {c.scanned[key].level}" if key in c.scanned else "born-digital"
            (out / r.filename).write_bytes(pdf)
            print(f"{out / r.filename}  ({len(pdf):,} bytes, {note}, {len(r.placed)} placed)")
    text = json.dumps(manifest(corpora), ensure_ascii=False, indent=2) + "\n"
    (root / "manifest.json").write_text(text, encoding="utf-8", newline="\n")
    print(root / "manifest.json")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
