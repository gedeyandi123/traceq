"""A stored export that cannot be re-rendered says why, instead of failing with a bare error."""

from __future__ import annotations

import hashlib

import pytest

from traceq.reports import (
    TYPST_VERSION,
    ReportNotReproducible,
    check_render_inputs,
    check_rendered_pdf,
)

SUPPORTED = ("1.0.0",)


def test_matching_versions_pass() -> None:
    check_render_inputs(
        template_version="1.0.0", typst_version=TYPST_VERSION, supported_templates=SUPPORTED
    )


def test_other_typst_version_names_stored_and_running() -> None:
    with pytest.raises(ReportNotReproducible) as err:
        check_render_inputs(
            template_version="1.0.0", typst_version="0.0.1", supported_templates=SUPPORTED
        )
    assert "0.0.1" in str(err.value)
    assert TYPST_VERSION in str(err.value)
    assert "Typst" in str(err.value)


def test_unsupported_template_version_is_named() -> None:
    with pytest.raises(ReportNotReproducible, match=r"template version 7\.0\.0"):
        check_render_inputs(
            template_version="7.0.0", typst_version=TYPST_VERSION, supported_templates=SUPPORTED
        )


def test_sha_mismatch_is_refused_and_match_passes() -> None:
    pdf = b"%PDF-1.7 golden"
    check_rendered_pdf(pdf, hashlib.sha256(pdf).hexdigest())
    with pytest.raises(ReportNotReproducible, match="SHA-256"):
        check_rendered_pdf(pdf, "0" * 64)
