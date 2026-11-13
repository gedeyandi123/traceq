"""Vendor Assessments (TP-201, TP-202) and the TP-202 VMP (ticket #52, spec #29).

Coverage condition 1 (design section 6) needs a Vendor Assessment the system can cite:
without one in the corpus it always fails. The TP-201 vendor is assessed with full scope,
the TP-202 vendor with limited scope (mechanical yes, control system/software no). The
TP-202 VMP lists the documents TP-202 requires, so its expected IQ/OQ gaps have a source.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from traceq_dataset.render import (
    EVAL_T0,
    Rendered,
    RenderError,
    render_vendor_assessment,
    render_vmp,
)
from traceq_dataset.schema import Document, Equipment
from traceq_dataset.validate import missing_text, page_texts
from traceq_dataset.world import load

WORLD = Path(__file__).parents[1] / "world"


@pytest.fixture(scope="module")
def tp201() -> Equipment:
    return load(WORLD / "tp201.yaml")


@pytest.fixture(scope="module")
def tp202() -> Equipment:
    return load(WORLD / "tp202.yaml")


def _doc(eq: Equipment, type_: str) -> Document:
    docs = [d for d in eq.documents if d.type == type_]
    assert len(docs) == 1, type_
    return docs[0]


def _assessment(eq: Equipment) -> Rendered:
    return render_vendor_assessment(eq, _doc(eq, "vendor_assessment").id, EVAL_T0)


def _text(r: Rendered) -> str:
    return " ".join(page_texts(r.pdf))


def _with(eq: Equipment, edit) -> Equipment:
    data = eq.model_dump(mode="json")
    edit(data)
    return Equipment.model_validate(data)


# --- Vendor Assessment ----------------------------------------------------------------


@pytest.mark.parametrize("name", ["tp201", "tp202"])
def test_assessment_renders_every_area(name: str, request: pytest.FixtureRequest) -> None:
    eq: Equipment = request.getfixturevalue(name)
    va = _assessment(eq)
    assert missing_text(va) == []
    assert set(va.placed) == {
        f"scope.{s}" for s in ("mechanical", "control", "data_integrity", "documentation")
    }
    text = _text(va)
    assert eq.vendor.name in text
    assert eq.tag in text


def test_tp201_vendor_assessed_with_full_scope(tp201: Equipment) -> None:
    text = _text(_assessment(tp201))
    for row in (
        "Mekanik (mechanical) Ya",
        "Sistem kendali dan perangkat lunak (control system/software) Ya",
        "Integritas data (data integrity) Ya",
        "Dokumentasi (documentation) Ya",
    ):
        assert row in text, row
    assert "Tidak" not in text


def test_tp202_vendor_assessed_with_limited_scope(tp202: Equipment) -> None:
    """Design section 6: mechanical yes, control system/software no."""
    text = _text(_assessment(tp202))
    for row in (
        "Mekanik (mechanical) Ya",
        "Sistem kendali dan perangkat lunak (control system/software) Tidak",
        "Integritas data (data integrity) Tidak",
        "Dokumentasi (documentation) Ya",
    ):
        assert row in text, row


@pytest.mark.parametrize("name", ["tp201", "tp202"])
def test_assessment_is_dated_by_the_assessment(name: str, request: pytest.FixtureRequest) -> None:
    eq: Equipment = request.getfixturevalue(name)
    assert eq.vendor.assessment is not None
    assert _doc(eq, "vendor_assessment").issued_on == eq.vendor.assessment.assessed_on


def test_assessment_states_the_reliance_rule(tp201: Equipment) -> None:
    """The scope is what the site may rely on (CPOB Ch. 12), in the document's own words."""
    text = _text(_assessment(tp201))
    assert "CPOB Bab 12" in text
    assert "Bukti" in text


def test_assessment_needs_an_assessed_vendor(tp202: Equipment) -> None:
    def edit(d: dict) -> None:
        d["vendor"]["assessment"] = None

    with pytest.raises(ValidationError, match=r"vendor_assessment needs vendor\.assessment"):
        _with(tp202, edit)


def test_assessment_date_must_match(tp202: Equipment) -> None:
    def edit(d: dict) -> None:
        for doc in d["documents"]:
            if doc["type"] == "vendor_assessment":
                doc["issued_on"] = "T0-1d"

    with pytest.raises(ValidationError, match=r"issued_on is not vendor\.assessment\.assessed_on"):
        _with(tp202, edit)


def test_assessment_refuses_an_unknown_scope(tp202: Equipment) -> None:
    assert tp202.vendor.assessment is not None
    odd = tp202.model_copy(
        update={
            "vendor": tp202.vendor.model_copy(
                update={
                    "assessment": tp202.vendor.assessment.model_copy(
                        update={"scope": frozenset({"mechanical", "cleaning"})}
                    )
                }
            )
        }
    )
    with pytest.raises(RenderError, match="cleaning"):
        _assessment(odd)


# --- TP-202 VMP -----------------------------------------------------------------------


def test_tp202_vmp_lists_its_required_documents(tp202: Equipment) -> None:
    vmp = render_vmp(tp202, _doc(tp202, "vmp").id, EVAL_T0)
    assert missing_text(vmp) == []
    assert set(vmp.placed) == {f"required.{d.id}" for d in tp202.required_documents}
    text = _text(vmp)
    assert "IQ-TP202 Protokol IQ IQ" in text
    assert "OQ-TP202 Protokol OQ OQ" in text


# --- Not on any required-document list -------------------------------------------------


@pytest.mark.parametrize("name", ["tp201", "tp202"])
def test_new_documents_are_not_required_documents(
    name: str, request: pytest.FixtureRequest
) -> None:
    eq: Equipment = request.getfixturevalue(name)
    required = {d.id for d in eq.required_documents}
    site = {d.id for d in eq.documents if d.type in Document.GOVERNING_TYPES}
    assert _doc(eq, "vendor_assessment").id in site
    assert site.isdisjoint(required)
