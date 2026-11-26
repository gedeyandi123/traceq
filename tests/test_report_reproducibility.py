"""A stored export that cannot be re-rendered says why, instead of failing with a bare error.

Only an unsupported template refuses before rendering. A Typst version that differs from the
running one is not a refusal by itself: the SHA-256 of the re-render decides, and the Typst
versions are named as the likely cause only when the SHA does not match.
"""

from __future__ import annotations

import hashlib

import pytest

from traceq.reports import (
    TYPST_VERSION,
    ReportNotReproducible,
    check_rendered_pdf,
    check_template_supported,
)

SUPPORTED = ("1.0.0",)
PDF = b"%PDF-1.7 golden"
PDF_SHA = hashlib.sha256(PDF).hexdigest()


def test_supported_template_passes() -> None:
    check_template_supported("1.0.0", SUPPORTED)


def test_unsupported_template_version_is_named() -> None:
    with pytest.raises(ReportNotReproducible, match=r"template version 7\.0\.0"):
        check_template_supported("7.0.0", SUPPORTED)


def test_matching_sha_passes_whatever_typst_version_was_stored() -> None:
    check_rendered_pdf(PDF, PDF_SHA, stored_typst_version=TYPST_VERSION)
    check_rendered_pdf(PDF, PDF_SHA, stored_typst_version="0.0.1")


def test_sha_mismatch_with_other_typst_names_stored_and_running_version() -> None:
    with pytest.raises(ReportNotReproducible) as err:
        check_rendered_pdf(PDF, "0" * 64, stored_typst_version="0.0.1")
    assert "SHA-256" in str(err.value)
    assert "0.0.1" in str(err.value)
    assert TYPST_VERSION in str(err.value)


def test_sha_mismatch_with_same_typst_says_it_cannot_be_verified() -> None:
    with pytest.raises(ReportNotReproducible, match="cannot be verified") as err:
        check_rendered_pdf(PDF, "0" * 64, stored_typst_version=TYPST_VERSION)
    assert "SHA-256" in str(err.value)
    assert "0.0.1" not in str(err.value)
