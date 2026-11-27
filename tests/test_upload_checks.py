"""The checks an uploaded Protocol Draft passes before it is queued, the package built for its
run, and the text the report can typeset (spec #375, ticket S5)."""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pypdf import PdfWriter

from traceq.audit import Actor
from traceq.documents.package import ReviewPackage
from traceq.reports import (
    PreReviewReportSnapshot,
    ReportFinding,
    ReportKindSummary,
    render_pre_review_pdf,
    snapshot_hash,
    typesettable,
    typesettable_snapshot,
)
from traceq.uploads import UploadSettings
from traceq.uploads.checks import Refused, TooLarge, check_pdf, sha256_of
from traceq.uploads.runner import draft_doc_id, write_package
from traceq.uploads.store import Job, blob_path, save_blob, usd


def pdf(pages: int = 1, marker: str = "", side: float = 200) -> bytes:
    """A readable PDF of ``pages`` blank square pages; ``marker`` makes its bytes differ."""
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=side, height=side)
    writer.add_metadata({"/Title": marker or "draft"})
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def test_a_pdf_within_the_caps_is_accepted_and_named_by_its_hash() -> None:
    data = pdf(3)
    checked = check_pdf(data, max_pages=5)
    assert (checked.pages, checked.size_bytes) == (3, len(data))
    assert checked.sha256 == sha256_of(data)


@pytest.mark.parametrize(
    "data",
    [b"", b"hello", b"PK\x03\x04 a zip", b"<html>%PDF-</html>", b"\x00%PDF-1.4"],
)
def test_a_file_that_is_not_a_pdf_is_refused(data: bytes) -> None:
    with pytest.raises(Refused):
        check_pdf(data)


def test_a_file_with_the_signature_that_cannot_be_read_is_refused() -> None:
    with pytest.raises(Refused, match="PDF"):
        check_pdf(b"%PDF-1.7\nthis is not a pdf body at all")


def test_an_oversize_file_is_refused_before_it_is_read() -> None:
    with pytest.raises(TooLarge):
        check_pdf(pdf(1), max_bytes=100)


def test_a_pdf_over_the_page_cap_is_refused() -> None:
    with pytest.raises(Refused, match="cap is 2"):
        check_pdf(pdf(3), max_pages=2)


def test_a_page_that_declares_a_huge_size_is_refused_before_it_is_decoded() -> None:
    huge = pdf(1, side=200_000)
    assert len(huge) < 2_000  # a tiny file that would rasterise to gigapixels
    with pytest.raises(Refused, match=r"page 1 is .* the cap is 3600"):
        check_pdf(huge)


def test_the_page_size_cap_is_per_side_and_configurable() -> None:
    assert check_pdf(pdf(1, side=842)).pages == 1
    with pytest.raises(Refused, match="page 1"):
        check_pdf(pdf(1, side=842), max_page_points=800)


def test_pages_that_render_to_too_many_pixels_together_are_refused() -> None:
    data = pdf(5, side=842)
    assert check_pdf(data, max_render_pixels=100_000_000).pages == 5
    with pytest.raises(Refused, match="too large together"):
        check_pdf(data, max_render_pixels=20_000_000)


def test_bytes_are_stored_under_their_hash_and_never_twice(tmp_path: Path) -> None:
    data = pdf(1)
    sha = sha256_of(data)
    path = save_blob(tmp_path / "files", sha, data)
    assert path == blob_path(tmp_path / "files", sha) == tmp_path / "files" / f"{sha}.pdf"
    assert path.read_bytes() == data
    assert save_blob(tmp_path / "files", sha, data) == path
    assert [p.name for p in (tmp_path / "files").iterdir()] == [f"{sha}.pdf"]


@pytest.mark.parametrize("name", ["../x", "a" * 63, "A" * 64, "x/../" + "a" * 59])
def test_a_name_that_is_not_a_hash_is_never_a_path(tmp_path: Path, name: str) -> None:
    with pytest.raises(ValueError):
        blob_path(tmp_path, name)


# --- The package of one uploaded revision -----------------------------------------------


def test_the_run_of_an_upload_reads_a_one_document_review_package(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "manifest.json").write_text(json.dumps({"version": "0.1.1"}), encoding="utf-8")
    data = pdf(2)
    sha = sha256_of(data)
    stored = save_blob(tmp_path / "files", sha, data)
    settings = UploadSettings(
        equipment="TP-201",
        store=tmp_path,
        corpus=corpus,
        recordings=tmp_path / "r",
        package_recordings=tmp_path / "p",
        model="m",
    )
    job = Job(
        id=7,
        at=datetime(2026, 11, 27, tzinfo=UTC),
        equipment="TP-201",
        rev=3,
        sha256=sha,
        size_bytes=len(data),
        pages=2,
        status="running",
        reserved_usd=usd(0),
        cost_usd=None,
        run_id=None,
        message=None,
        started_at=None,
        finished_at=None,
        actor=Actor(subject="s", issuer="i", name="n"),
    )
    package = ReviewPackage.load(write_package(settings, job, stored, tmp_path / "pkg"))
    package.check_fits(corpus, "TP-201")
    doc = package.draft(3)
    assert (doc.doc_id, doc.rev, doc.sha256) == (draft_doc_id("TP-201"), 3, sha)
    assert doc.path.read_bytes() == data
    assert draft_doc_id("TP-201") == "OQ-TP201"
    with pytest.raises(ValueError, match="no draft revision 0"):
        package.draft(0)


# --- Text outside the bundled fonts -----------------------------------------------------


def test_text_is_kept_when_the_bundled_fonts_draw_it() -> None:
    text = "Gaya tekan ≥ 100 kN ± 5 %, 20–60 rpm, 3 µm, αβ, Привет, é\nbaris dua"
    assert typesettable(text) == text


def test_text_the_fonts_cannot_draw_is_replaced_or_dropped() -> None:
    assert typesettable("a漢b😀c") == "a�b�c"
    assert typesettable("x\x00y\x07z​w‮v") == "xyzwv"
    assert typesettable("lone \ud800 surrogate") == "lone  surrogate"


def _snapshot(detail: str) -> PreReviewReportSnapshot:
    zero = ReportKindSummary(
        total=1, decided=0, accepted=0, edited=0, rejected=0, undecided=1, changed=0
    )
    return PreReviewReportSnapshot(
        generated_at=datetime(2026, 11, 27, 9, 0, tzinfo=UTC),
        equipment="TP-201",
        run_id="r1",
        round_number=1,
        round_status="open",
        coverage=zero,
        findings_summary=zero,
        draft_findings=(
            ReportFinding(
                position=0,
                finding_type="unit_error",
                detail=detail,
                citations=(detail,),
                state="undecided",
            ),
        ),
    )


def test_a_report_with_text_outside_the_fonts_is_typeset_and_hashable() -> None:
    hostile = "批准 😀 \x00 Ω ≥ ‮ \ud83d lone"
    snapshot = typesettable_snapshot(_snapshot(hostile))
    assert "批" not in snapshot.draft_findings[0].detail
    assert snapshot_hash(snapshot) == snapshot_hash(typesettable_snapshot(snapshot))
    pdf_bytes = render_pre_review_pdf(snapshot)
    assert pdf_bytes.startswith(b"%PDF")
    # A snapshot stored before the scrub still renders, deterministically.
    raw = _snapshot("批准 😀 \x00 Ω")
    assert render_pre_review_pdf(raw) == render_pre_review_pdf(raw)
