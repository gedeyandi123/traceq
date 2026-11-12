"""Render world data to born-digital PDF with Typst (design section 8).

Python formats every string (numbers and dates in the document language), so the
expected text is known exactly; the Typst templates in ``templates/`` only lay it out.
Output is deterministic for a given T0: no system fonts (Typst's bundled fonts only)
and PDF metadata dates fixed to the document's issue date.

Usage::

    uv run python -m traceq_dataset.render world/tp201.yaml [--t0 YYYY-MM-DD] [--out dist]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import typst

from traceq_dataset.schema import (
    Document,
    Equipment,
    OneOfSpec,
    RangeSpec,
    Requirement,
    Spec,
)

TEMPLATES = Path(__file__).parent / "templates"
EVAL_T0 = dt.date(2026, 6, 1)
"""Fixed T0 of the eval corpus (design section 4, "Dates")."""


class RenderError(ValueError):
    """World data cannot be rendered (pending values, unknown document)."""


@dataclass(frozen=True)
class Placed:
    """A string the renderer drew, and the page it is on (1-based)."""

    page: int
    text: str


@dataclass(frozen=True)
class Rendered:
    doc_id: str
    rev: int
    pdf: bytes
    requirements: Mapping[str, Placed]

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


def _compile(template: str, data: dict, issued: dt.date) -> tuple[bytes, list[dict]]:
    inputs = {"data": json.dumps(data, ensure_ascii=False)}
    common = {"root": TEMPLATES, "ignore_system_fonts": True, "sys_inputs": inputs}
    path = TEMPLATES / template
    timestamp = int(dt.datetime.combine(issued, dt.time(), dt.UTC).timestamp())
    pdf, warnings = typst.compile_with_warnings(path, timestamp=timestamp, **common)
    if warnings:
        raise RenderError(f"{template}: Typst warnings: {warnings}")
    placed = json.loads(typst.query(path, "<req>", field="value", **common))
    return pdf, placed


def render_urs(eq: Equipment, rev: int, t0: dt.date) -> Rendered:
    """URS (SKP) revision ``rev``. Rev 0 uses ``superseded_spec`` where one is set."""
    pending = eq.pending()
    if pending:
        raise RenderError(f"{eq.tag}: {len(pending)} pending value(s), e.g. {pending[0]}")
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
        "equipment": f"{eq.tag} \N{EN DASH} {eq.name}",
        "purpose": (
            f"Dokumen ini menetapkan kebutuhan pengguna untuk {eq.tag}. Persyaratan dengan "
            "Kritis = Ya berdampak langsung pada mutu produk, keselamatan, atau integritas data."
        ),
        "sections": [{"title": t, "requirements": rs} for t, rs in sections.items()],
        "history": history,
        "signatures": [
            {
                "role": role,
                "name": people[pid],
                "signature": "Ditandatangani elektronik",
                "date": fmt_date(issued, lang),
            }
            for role, pid in roles
        ],
    }
    pdf, placed = _compile("urs.typ", data, issued)
    pages = {p["id"]: p["page"] for p in placed}
    return Rendered(
        doc_id=doc.id,
        rev=rev,
        pdf=pdf,
        requirements={rid: Placed(pages[rid], text) for rid, text in texts.items()},
    )


def render_all(eq: Equipment, t0: dt.date) -> list[Rendered]:
    return [render_urs(eq, d.rev, t0) for d in eq.documents if d.type == "urs"]


def main(argv: list[str]) -> int:
    from traceq_dataset.world import load

    parser = argparse.ArgumentParser(prog="traceq_dataset.render")
    parser.add_argument("world", type=Path)
    parser.add_argument("--t0", type=dt.date.fromisoformat, default=EVAL_T0)
    parser.add_argument("--out", type=Path, default=Path("dist"))
    args = parser.parse_args(argv)

    eq = load(args.world)
    out = args.out / f"t0-{args.t0.isoformat()}" / eq.tag
    out.mkdir(parents=True, exist_ok=True)
    for r in render_all(eq, args.t0):
        (out / r.filename).write_bytes(r.pdf)
        print(f"{out / r.filename}  ({len(r.pdf):,} bytes, {len(r.requirements)} requirements)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
