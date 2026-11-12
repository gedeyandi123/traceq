"""Design documents and certificates of TP-201: datasheet, functional spec, risk assessment,
material and calibration certificates, and DQ report."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from traceq_dataset.answer_key import derive
from traceq_dataset.corpus import Corpus, build_corpus
from traceq_dataset.coverage import meets
from traceq_dataset.render import (
    EVAL_T0,
    RA_SHEET,
    Rendered,
    design_field,
    render_calibration_certificate,
    render_datasheet,
    render_dq,
    render_functional_spec,
    render_material_certificate,
    render_risk_assessment,
)
from traceq_dataset.schema import Equipment, RangeObs, RangeSpec
from traceq_dataset.validate import cell_texts, missing_text, page_texts
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


def test_force_sensor_certificate_from_the_vendor(eq: Equipment) -> None:
    """CAL-TP201-01: the vendor calibrates the press's two force channels before the FAT;
    still valid at the SAT, and no main-channel error above FAT-M-08's 0.5% FS."""
    cal = render_calibration_certificate(eq, "CAL-TP201-01", EVAL_T0)
    assert missing_text(cal) == []
    assert cal.placed["instrument"].text == "FMS-TP201"
    text = page_texts(cal.pdf)[0]
    assert "Pressora Maschinenbau GmbH" in text
    assert "Main compression 100 100.42 +0.42 ± 0.3" in text
    assert "Pre-compression 20 20.07 +0.07 ± 0.06" in text
    fms = next(i for i in eq.instruments if i.id == "FMS-TP201")
    cert, dates = fms.certificate, {p.doc_id: p for p in eq.protocols}
    assert cert.calibrated_on < dates["FAT-TP201-M"].executed_on
    assert cert.valid_until > dates["SAT-TP201"].executed_on
    assert cert.results is not None
    main = [p for p in cert.results.points if p.channel == "Main compression"]
    assert max(abs(p.reading - p.nominal) for p in main) <= 0.5


def test_calibration_readings_await_review(eq: Equipment) -> None:
    assert {i.id for i in eq.unreviewed_results()} == {"TACH-07", "SW-03", "FMS-TP201"}


# --- Functional design specification --------------------------------------------------


@pytest.fixture(scope="module")
def fds(eq: Equipment) -> Rendered:
    return render_functional_spec(eq, "FDS-TP201", EVAL_T0)


def test_fds_describes_every_control_and_data_integrity_requirement(
    eq: Equipment, fds: Rendered
) -> None:
    """Gap requirements included (door interlock, recipe backup, time sync): designed, not
    tested, so their Coverage stays `gap`."""
    facts = [f for f in eq.designs if f.doc_id == "FDS-TP201"]
    scopes = {r.id for r in eq.requirements if r.scope in ("control", "data_integrity")}
    assert {f.requirement for f in facts} == scopes
    assert set(fds.placed) == {design_field(eq, f) for f in facts}
    assert missing_text(fds) == []
    text = " ".join(page_texts(fds.pdf))
    assert "URS-" not in text
    assert "5.1 Guard door interlock" in text


def test_fds_states_no_new_numbers(eq: Equipment) -> None:
    """Every FDS fact meets the URS, and a numeric one repeats the datasheet's value."""
    reqs = {r.id: r for r in eq.requirements}
    ds = {f.requirement: f.observed for f in eq.designs if f.doc_id == "DS-TP201"}
    for f in eq.designs:
        if f.doc_id == "FDS-TP201":
            assert meets(reqs[f.requirement].spec, f.observed), f.requirement
            if f.observed.type != "present":
                assert f.observed == ds[f.requirement]


def test_fds_needs_descriptions(eq: Equipment) -> None:
    def edit(d: dict) -> None:
        for f in d["designs"]:
            if f["doc_id"] == "FDS-TP201":
                f["description"] = None

    with pytest.raises(ValidationError, match="needs a label, section and description"):
        _with(eq, edit)


# --- Risk assessment ------------------------------------------------------------------


@pytest.fixture(scope="module")
def ra(eq: Equipment) -> Rendered:
    return render_risk_assessment(eq, "RA-TP201", EVAL_T0)


def test_risk_assessment_marks_the_urs_critical_aspects(eq: Equipment, ra: Rendered) -> None:
    assert ra.filename == "RA-TP201_rev0.xlsx"
    assert missing_text(ra) == []
    marked = {r.id for r in eq.requirements if ra.placed[f"{r.id}.critical"].text == "Ya"}
    assert marked == {r.id for r in eq.requirements if r.critical}
    assert len(marked) == 11


def test_risk_assessment_is_values_not_formulas(ra: Rendered) -> None:
    cells = cell_texts(ra.data)
    assert not any(v.startswith("=") for v in cells.values())
    rpn = ra.placed["URS-TP201-015.rpn"]
    assert (rpn.sheet, cells[(RA_SHEET, rpn.cell or "")]) == (RA_SHEET, "40")
    assert "URS-TP201 rev 1 (SKP)" in cells.values()


def test_risk_assessment_bytes_are_deterministic(eq: Equipment, ra: Rendered) -> None:
    assert render_risk_assessment(eq, "RA-TP201", EVAL_T0).data == ra.data
    later = render_risk_assessment(eq, "RA-TP201", EVAL_T0.replace(year=2027))
    assert later.data != ra.data


def test_risk_scores_await_review(eq: Equipment) -> None:
    assert eq.unreviewed_risks()


def test_risk_assessment_must_agree_with_the_urs(eq: Equipment) -> None:
    def edit(d: dict) -> None:
        d["risk_assessment"]["rows"][0]["severity"] = 5  # URS-TP201-001 is not critical

    with pytest.raises(ValidationError, match="URS-TP201-001 severity 5 disagrees"):
        _with(eq, edit)


def test_risk_assessment_covers_every_requirement(eq: Equipment) -> None:
    def edit(d: dict) -> None:
        d["risk_assessment"]["rows"] = d["risk_assessment"]["rows"][1:]

    with pytest.raises(ValidationError, match="RA-TP201: no row for URS-TP201-001"):
        _with(eq, edit)


def test_requirements_carry_their_risk_row(corpus: Corpus) -> None:
    reqs = derive(corpus)["requirements.yaml"]
    risk = next(r for r in reqs if r["id"] == "URS-TP201-018")["risk"]
    assert risk == {
        "doc": "RA-TP201",
        "rev": 0,
        "sheet": RA_SHEET,
        "row": 27,
        "text": "Ya",
        "critical": True,
        "severity": 5,
        "occurrence": 2,
        "detection": 3,
        "rpn": 30,
    }


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

    with pytest.raises(ValidationError, match="TACH-07: unknown issuer lab-99"):
        _with(eq, edit)


def test_dq_reviews_rendered_documents(eq: Equipment) -> None:
    def edit(d: dict) -> None:
        for doc in d["documents"]:
            if doc["id"] == "DQ-TP201":
                doc["reviews"][1]["rev"] = 3

    with pytest.raises(ValidationError, match="reviews DS-TP201 rev 3, which is not rendered"):
        _with(eq, edit)
