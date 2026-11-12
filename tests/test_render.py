"""Typst renderer and semantic validator: URS-TP201 rev 0/1 and the FAT documents."""

from __future__ import annotations

import datetime as dt
import io
from pathlib import Path

import pytest
from pydantic import ValidationError
from pypdf import PdfReader

from traceq_dataset.render import (
    EVAL_T0,
    Rendered,
    RenderError,
    fmt_date,
    fmt_number,
    fmt_observation,
    fmt_spec,
    render_all,
    render_fat,
    render_urs,
)
from traceq_dataset.schema import Equipment, PendingSpec, PresentObs, RangeObs, RangeSpec
from traceq_dataset.validate import missing_text, page_texts
from traceq_dataset.world import load

TP201 = Path(__file__).parents[1] / "world" / "tp201.yaml"


@pytest.fixture(scope="module")
def eq() -> Equipment:
    return load(TP201)


@pytest.fixture(scope="module")
def rev1(eq: Equipment) -> Rendered:
    return render_urs(eq, 1, EVAL_T0)


@pytest.mark.parametrize(
    ("value", "lang", "expected"),
    [
        (120000, "id", "120.000"),
        (120000, "en", "120,000"),
        (0.8, "id", "0,8"),
        (0.8, "en", "0.8"),
        (20.4, "id", "20,4"),
        (36, "id", "36"),
    ],
)
def test_fmt_number(value: float, lang: str, expected: str) -> None:
    assert fmt_number(value, lang) == expected


def test_fmt_date() -> None:
    day = dt.date(2026, 3, 12)
    assert fmt_date(day, "id") == "12/03/2026"
    assert fmt_date(day, "en") == "12-Mar-2026"


def test_every_requirement_on_its_page(eq: Equipment, rev1: Rendered) -> None:
    assert set(rev1.placed) == {r.id for r in eq.requirements}
    assert missing_text(rev1) == []


def test_deterministic_with_fixed_metadata_date(eq: Equipment, rev1: Rendered) -> None:
    assert render_urs(eq, 1, EVAL_T0).pdf == rev1.pdf
    meta = PdfReader(io.BytesIO(rev1.pdf)).metadata
    issued = next(d for d in eq.documents if d.rev == 1).issued_on.resolve(EVAL_T0)
    assert meta["/CreationDate"] == f"D:{issued:%Y%m%d}000000Z"


def test_t0_moves_dates(eq: Equipment, rev1: Rendered) -> None:
    later = render_urs(eq, 1, EVAL_T0 + dt.timedelta(days=30))
    assert later.pdf != rev1.pdf
    assert later.placed == rev1.placed


def test_rev0_uses_superseded_value(eq: Equipment, rev1: Rendered) -> None:
    """S8: one value differs between rev 0 and rev 1."""
    rev0 = render_urs(eq, 0, EVAL_T0)
    assert missing_text(rev0) == []
    changed = {rid for rid, p in rev0.placed.items() if p.text != rev1.placed[rid].text}
    assert changed == {"URS-TP201-003"}
    assert "100.000" in rev0.placed["URS-TP201-003"].text
    assert "120.000" in rev1.placed["URS-TP201-003"].text


def test_refuses_pending(eq: Equipment) -> None:
    first = eq.requirements[0].model_copy(update={"spec": PendingSpec(expected="range")})
    skeleton = eq.model_copy(update={"requirements": (first, *eq.requirements[1:])})
    with pytest.raises(RenderError, match="pending"):
        render_urs(skeleton, 1, EVAL_T0)


def test_unknown_revision(eq: Equipment) -> None:
    with pytest.raises(RenderError, match="rev 9"):
        render_urs(eq, 9, EVAL_T0)


# --- Document schema ------------------------------------------------------------------


def _with_documents(eq: Equipment, *docs: dict) -> None:
    data = eq.model_dump(mode="json")
    Equipment.model_validate({**data, "documents": list(docs)})


DOC = {
    "id": "URS-TP201",
    "rev": 0,
    "type": "urs",
    "language": "id",
    "issued_on": "T0-260d",
    "prepared_by": "p-qe",
    "checked_by": "p-qs",
    "approved_by": "p-qa",
}


def test_document_unknown_person(eq: Equipment) -> None:
    with pytest.raises(ValidationError, match="unknown approved_by"):
        _with_documents(eq, {**DOC, "approved_by": "p-nobody"})


def test_document_revision_needs_change_note(eq: Equipment) -> None:
    with pytest.raises(ValidationError, match="change_note"):
        _with_documents(eq, DOC, {**DOC, "rev": 1})


def test_duplicate_document_revision(eq: Equipment) -> None:
    with pytest.raises(ValidationError, match="duplicate document"):
        _with_documents(eq, DOC, DOC)


# --- FAT ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        (RangeSpec(min=20, max=60, unit="rpm"), "20–60 rpm"),
        (RangeSpec(min=100, unit="kN"), "≥ 100 kN"),
        (RangeSpec(max=0.8, unit="µm"), "≤ 0.8 µm"),
        (RangeSpec(min=380, max=380, unit="V"), "380 V"),
    ],
)
def test_fmt_spec(spec: RangeSpec, expected: str) -> None:
    assert fmt_spec(spec, "en") == expected


def test_fmt_observation() -> None:
    assert fmt_observation(RangeObs(min=20, max=60, unit="rpm"), "en") == "20–60 rpm"
    assert fmt_observation(PresentObs(value=False), "en") == "Not present"


@pytest.fixture(scope="module")
def fat_m(eq: Equipment) -> Rendered:
    return render_fat(eq, "FAT-TP201-M", EVAL_T0)


def test_every_document_validates(eq: Equipment) -> None:
    rendered = render_all(eq, EVAL_T0)
    assert {r.filename for r in rendered} == {
        "URS-TP201_rev0.pdf",
        "URS-TP201_rev1.pdf",
        "FAT-TP201-M_rev0.pdf",
        "FAT-TP201-C_rev0.pdf",
    }
    assert [p for r in rendered for p in missing_text(r)] == []


def test_fat_places_every_step(eq: Equipment, fat_m: Rendered) -> None:
    steps = {t.step for t in eq.tests if t.protocol == "FAT-TP201-M"}
    assert set(fat_m.placed) == {f"{s}.{k}" for s in steps for k in ("acceptance", "observed")}


def test_fat_vendor_acceptance_overrides_urs(fat_m: Rendered) -> None:
    """FAT-M-02 tests the vendor's 20–60 rpm, narrower than the URS 20–70 (partial)."""
    assert fat_m.placed["FAT-M-02.acceptance"].text == "20–60 rpm"


def test_s5_out_of_limit_marked_pass(fat_m: Rendered) -> None:
    assert fat_m.placed["FAT-M-03.acceptance"].text == "≥ 100 kN"
    assert fat_m.placed["FAT-M-03.observed"].text == "96 kN"


def test_s4_control_fat_has_no_site_approval(eq: Equipment) -> None:
    fat_c = render_fat(eq, "FAT-TP201-C", EVAL_T0)
    text = " ".join(page_texts(fat_c.pdf))
    site = {p.name for p in eq.people if p.id in {"p-qs", "p-qa"}}
    assert not any(name in text for name in site)
    executed = next(p for p in eq.protocols if p.doc_id == "FAT-TP201-C").executed_on
    assert fmt_date(executed.resolve(EVAL_T0), "en") in text


def test_fat_requires_description(eq: Equipment) -> None:
    tests = tuple(
        t.model_copy(update={"description": None}) if t.step == "FAT-M-01" else t for t in eq.tests
    )
    with pytest.raises(RenderError, match="FAT-M-01: needs a description"):
        render_fat(eq.model_copy(update={"tests": tests}), "FAT-TP201-M", EVAL_T0)


def test_fat_approval_must_match_protocol(eq: Equipment) -> None:
    data = eq.model_dump(mode="json")
    for d in data["documents"]:
        if d["id"] == "FAT-TP201-C":
            d["approved_by"] = "p-qa"
    with pytest.raises(ValidationError, match="site approval"):
        Equipment.model_validate(data)
