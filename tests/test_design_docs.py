"""Datasheet, material and calibration certificates, and DQ report of TP-201."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from traceq_dataset.answer_key import derive
from traceq_dataset.corpus import Corpus, build_corpus
from traceq_dataset.coverage import meets
from traceq_dataset.render import (
    EVAL_T0,
    Rendered,
    design_field,
    render_calibration_certificate,
    render_datasheet,
    render_dq,
    render_material_certificate,
)
from traceq_dataset.schema import Equipment, RangeObs, RangeSpec
from traceq_dataset.validate import missing_text, page_texts
from traceq_dataset.world import load

TP201 = Path(__file__).parents[1] / "world" / "tp201.yaml"


@pytest.fixture(scope="module")
def eq() -> Equipment:
    return load(TP201)


@pytest.fixture(scope="module")
def ds(eq: Equipment) -> Rendered:
    return render_datasheet(eq, "DS-TP201", EVAL_T0)


@pytest.fixture(scope="module")
def mtc(eq: Equipment) -> Rendered:
    return render_material_certificate(eq, "MTC-TP201-01", EVAL_T0)


@pytest.fixture(scope="module")
def dq(eq: Equipment) -> Rendered:
    return render_dq(eq, "DQ-TP201", EVAL_T0)


# --- Datasheet ------------------------------------------------------------------------


def test_datasheet_places_every_design_fact(eq: Equipment, ds: Rendered) -> None:
    facts = [f for f in eq.designs if f.doc_id == "DS-TP201"]
    assert set(ds.placed) == {"serial"} | {design_field(eq, f) for f in facts}
    assert missing_text(ds) == []
    assert len(page_texts(ds.pdf)) == 1


def test_datasheet_conflict_and_nameplate_serial(ds: Rendered) -> None:
    """URS-TP201-008 conflict (EU B vs EU D); S3: the datasheet has the nameplate serial."""
    assert ds.placed["tooling_type"].text == "EU B"
    assert ds.placed["serial"].text == "RTP36-25-0417"
    assert ds.placed["turret_speed"].text == "20–70 rpm"
    assert ds.placed["output_rate"].text == "151,200 tablets/h"


def test_design_range_meets_when_it_spans_the_urs() -> None:
    spec = RangeSpec(min=20, max=70, unit="rpm")
    assert meets(spec, RangeObs(min=20, max=70, unit="rpm"))
    assert not meets(spec, RangeObs(min=20, max=60, unit="rpm"))


# --- Material certificate (S6) --------------------------------------------------------


def test_s6_one_part_in_ss_304(eq: Equipment, mtc: Rendered) -> None:
    materials = {k: p.text for k, p in mtc.placed.items() if k.endswith(".material")}
    assert materials == {
        "item-1.material": "SS 316L",
        "item-2.material": "SS 304",
        "item-3.material": "SS 316L",
        "item-4.material": "SS 316L",
        "item-5.material": "SS 316L",
    }
    assert missing_text(mtc) == []
    text = page_texts(mtc.pdf)[0]
    assert "Feed frame housing SS 304 1.4301" in text


def test_material_certificate_is_a_scan_without_handwritten_fields(
    eq: Equipment, mtc: Rendered
) -> None:
    assert not any(p.handwritten for p in mtc.placed.values())
    assert next(d for d in eq.documents if d.id == "MTC-TP201-01").scan == "medium"


# --- Calibration certificates (S2) ----------------------------------------------------


def test_s2_certificate_expired_before_the_sat(eq: Equipment) -> None:
    kal = render_calibration_certificate(eq, "KAL-2025-0412", EVAL_T0)
    assert missing_text(kal) == []
    assert kal.placed["instrument"].text == "TACH-07"
    assert kal.placed["valid_until"].text == "17-May-2026"
    executed = next(p for p in eq.protocols if p.doc_id == "SAT-TP201").executed_on
    tach = next(i for i in eq.instruments if i.id == "TACH-07")
    assert tach.certificate.valid_until.resolve(EVAL_T0).isoformat() == "2026-05-17"
    assert executed.resolve(EVAL_T0).isoformat() == "2026-05-18"
    text = page_texts(kal.pdf)[0]
    assert "1,000 1,000.3 +0.3 ± 0.6" in text


def test_stopwatch_certificate_is_valid(eq: Equipment) -> None:
    kal = render_calibration_certificate(eq, "KAL-2026-0057", EVAL_T0)
    assert missing_text(kal) == []
    assert kal.placed["valid_until"].text == "01-Feb-2027"


def test_calibration_readings_await_review(eq: Equipment) -> None:
    assert {i.id for i in eq.unreviewed_results()} == {"TACH-07", "SW-03"}


# --- DQ report ------------------------------------------------------------------------


def test_dq_records_the_tooling_mismatch_as_open_item(dq: Rendered) -> None:
    text = " ".join(page_texts(dq.pdf))
    assert "Tidak sesuai (butir terbuka 1)" in text
    assert "Tidak sesuai (butir terbuka 2)" not in text
    assert 'URS-TP201-008: DS-TP201 mencantumkan "Tooling standard: EU B"' in text
    assert "kecuali 1 butir terbuka" in text


def test_dq_reviews_every_requirement(eq: Equipment, dq: Rendered) -> None:
    text = " ".join(page_texts(dq.pdf))
    assert all(r.id in text for r in eq.requirements)
    assert "URS-TP201-009 Semua bagian yang kontak dengan produk terbuat dari SS 316L." in text


# --- Answer key -----------------------------------------------------------------------


@pytest.fixture(scope="module")
def corpus(eq: Equipment) -> Corpus:
    return build_corpus(eq)


def test_design_evidence_is_located(corpus: Corpus) -> None:
    reqs = {r["id"]: r for r in derive(corpus)["requirements.yaml"]}
    [ds] = reqs["URS-TP201-008"]["design_evidence"]
    assert (ds["field"], ds["text"], ds["meets_urs"]) == ("tooling_type", "EU B", False)
    mtc = [e for e in reqs["URS-TP201-009"]["design_evidence"] if e["doc"] == "MTC-TP201-01"]
    [bad] = [e for e in mtc if not e["meets_urs"]]
    assert (bad["part"], bad["text"], bad["page"]) == ("Feed frame housing", "SS 304", 1)
    assert all("status" not in e for r in reqs.values() for e in r["design_evidence"])


# --- Schema ---------------------------------------------------------------------------


def _with(eq: Equipment, edit) -> Equipment:
    data = eq.model_dump(mode="json")
    edit(data)
    return Equipment.model_validate(data)


def test_datasheet_needs_design_facts(eq: Equipment) -> None:
    def edit(d: dict) -> None:
        d["designs"] = [f for f in d["designs"] if f["doc_id"] != "DS-TP201"]

    with pytest.raises(ValidationError, match="datasheet needs design facts"):
        _with(eq, edit)


def test_calibration_certificate_needs_an_instrument(eq: Equipment) -> None:
    def edit(d: dict) -> None:
        d["instruments"][1]["certificate"]["id"] = "KAL-2026-9999"

    with pytest.raises(ValidationError, match="no instrument has certificate KAL-2026-0057"):
        _with(eq, edit)


def test_calibration_certificate_signed_by_its_lab(eq: Equipment) -> None:
    def edit(d: dict) -> None:
        for doc in d["documents"]:
            if doc["id"] == "KAL-2025-0412":
                doc["prepared_by"] = "p-qe"

    with pytest.raises(ValidationError, match="prepared_by must work for lab-01"):
        _with(eq, edit)


def test_certificate_lab_must_exist(eq: Equipment) -> None:
    def edit(d: dict) -> None:
        d["instruments"][0]["certificate"]["lab"] = "lab-99"

    with pytest.raises(ValidationError, match="TACH-07: unknown lab lab-99"):
        _with(eq, edit)


def test_dq_reviews_rendered_documents(eq: Equipment) -> None:
    def edit(d: dict) -> None:
        for doc in d["documents"]:
            if doc["id"] == "DQ-TP201":
                doc["reviews"][1]["rev"] = 3

    with pytest.raises(ValidationError, match="reviews DS-TP201 rev 3, which is not rendered"):
        _with(eq, edit)
