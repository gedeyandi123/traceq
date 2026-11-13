"""Governing documents of the TP-201 world (design section 4): the Validation Master Plan
and the qualification SOP, rendered so the system reads the required-document list and the
site rules from the corpus, with citations, instead of from world data."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from traceq_dataset.render import EVAL_T0, Rendered, render_sop, render_vmp
from traceq_dataset.schema import Equipment
from traceq_dataset.validate import missing_text, page_texts
from traceq_dataset.world import load

TP201 = Path(__file__).parents[1] / "world" / "tp201.yaml"


@pytest.fixture(scope="module")
def eq() -> Equipment:
    return load(TP201)


def _doc_id(eq: Equipment, type_: str) -> str:
    return next(d.id for d in eq.documents if d.type == type_)


@pytest.fixture(scope="module")
def vmp(eq: Equipment) -> Rendered:
    return render_vmp(eq, _doc_id(eq, "vmp"), EVAL_T0)


@pytest.fixture(scope="module")
def sop(eq: Equipment) -> Rendered:
    return render_sop(eq, _doc_id(eq, "sop"), EVAL_T0)


def _text(r: Rendered) -> str:
    return " ".join(page_texts(r.pdf))


# --- VMP ------------------------------------------------------------------------------


def test_vmp_lists_every_required_document(eq: Equipment, vmp: Rendered) -> None:
    """One row per required document, in world-data order, each with its stage."""
    assert set(vmp.placed) == {f"required.{d.id}" for d in eq.required_documents}
    assert [vmp.placed[f"required.{d.id}"].text for d in eq.required_documents] == [
        d.id for d in eq.required_documents
    ]
    assert missing_text(vmp) == []
    pages = page_texts(vmp.pdf)
    for d in eq.required_documents:
        row = pages[vmp.placed[f"required.{d.id}"].page - 1]
        assert d.id in row


def test_vmp_rows_name_type_and_stage(vmp: Rendered) -> None:
    text = _text(vmp)
    for row in (
        "IQ-TP201 Protokol IQ IQ",
        "OQ-TP201 Protokol OQ OQ",
        "URS-TP201 Spesifikasi Kebutuhan Pengguna (SKP) Desain",
        "KAL-2025-0412 Sertifikat kalibrasi: Digital tachometer (TACH-07) SAT",
    ):
        assert row in text, row


def test_vmp_gives_no_scenario_away(vmp: Rendered) -> None:
    """World-data notes name scenarios (S2); the VMP prints its own descriptions."""
    text = _text(vmp)
    assert "(S2)" not in text
    assert "expected_gap" not in text


# --- SOP ------------------------------------------------------------------------------


SOP_RULES = ("signatories", "segregation", "gdp", "witness", "protocols")


def test_sop_states_the_site_rules(sop: Rendered) -> None:
    assert set(sop.placed) == set(SOP_RULES)
    assert missing_text(sop) == []
    text = _text(sop)
    assert "pelaksana tidak boleh sekaligus menjadi Saksi" in text
    assert "penyusun tidak boleh menyetujui dokumen yang disusunnya" in text
    assert "satu garis" in text and "paraf, tanggal" in text and "alasan" in text


def test_sop_witness_rule_follows_the_design_default(eq: Equipment, sop: Rendered) -> None:
    """[D] default: Test Steps that verify a Critical Aspect need a Witness."""
    assert eq.site_rules is not None and eq.site_rules.witness == "critical_aspects"
    assert "Aspek Kritis" in sop.placed["witness"].text


def test_sop_witness_rule_changes_by_re_rendering(eq: Equipment) -> None:
    assert eq.site_rules is not None
    all_steps = eq.model_copy(
        update={"site_rules": eq.site_rules.model_copy(update={"witness": "all"})}
    )
    rendered = render_sop(all_steps, _doc_id(eq, "sop"), EVAL_T0)
    assert "Setiap Langkah Uji" in rendered.placed["witness"].text


def test_sop_protocols_from_the_template(sop: Rendered) -> None:
    """[D] default: protocols come from the site template (no leftover defect)."""
    assert "templat" in sop.placed["protocols"].text


# --- Schema ---------------------------------------------------------------------------


def test_governing_documents_are_not_required_documents(eq: Equipment) -> None:
    """The VMP and SOP govern every Equipment; they are not part of its package."""
    required = {d.id for d in eq.required_documents}
    assert {_doc_id(eq, "vmp"), _doc_id(eq, "sop")}.isdisjoint(required)


def test_sop_needs_site_rules(eq: Equipment) -> None:
    data = eq.model_dump(mode="json")
    data.pop("site_rules")
    with pytest.raises(ValidationError, match="SOP-VAL-002 rev 2: sop needs site_rules"):
        Equipment.model_validate(data)
