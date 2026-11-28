"""Golden renders: a Typst bump or a template edit must fail CI, not production downloads.

A stored report export is verified on every download by re-rendering its ``snapshot_json`` and
comparing SHA-256 with the stored ``pdf_sha256`` (ADR 0007, ADR 0010). The re-render depends on
two things outside the snapshot: the Typst compiler and the template file. If either changes, every
export made before the change stops verifying. These tests pin both: each committed synthetic
snapshot (ADR 0001) must render to the committed SHA-256.

If one fails, do NOT edit the expected value. A released template version is frozen: copy the
template to a new ``_vN`` file, give it a new ``template_version`` and leave the old one untouched.
A Typst upgrade that changes these bytes also changes the bytes of every stored export: record it in
an ADR, because exports made under the old ``typst_version`` then answer 409 until regenerated.
(A Typst upgrade that keeps these bytes keeps old exports downloadable.)
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from traceq.reports import (
    PRE_REVIEW_TEMPLATE_VERSIONS,
    QUALIFICATION_TEMPLATE_VERSION,
    QUALIFICATION_TEMPLATE_VERSION_V1,
    QUALIFICATION_TEMPLATE_VERSIONS,
    TEMPLATE_VERSION,
    PreReviewReportSnapshot,
    PreReviewReportSnapshotV2,
    QualificationReportSnapshot,
    QualificationReportSnapshotV1,
    parse_pre_review_snapshot,
    parse_qualification_snapshot,
    render_pre_review_pdf,
    render_qualification_pdf,
)

FIXTURES = Path(__file__).parent / "fixtures" / "reports"
# Rendered with typst 0.15.2 and ``ignore_system_fonts=True``; see the module docstring.
PRE_REVIEW_V2_SHA256 = "80849e3bd3d5af84187a466b47d9ba7716eb4dad10625737cdb617bb7d457d45"
PRE_REVIEW_V1_SHA256 = "3b221354d989ee257f442429b72e5cc5f7946174a97eb28ee211a6e9ebb6ea7a"
QUALIFICATION_V1_SHA256 = "2d191823dc158c184b8c457c41855222163cf83f16befaade365a99a836f2ed3"
QUALIFICATION_V2_SHA256 = "2c8f7cb4b6f56810c13f71b286f94416a9c15cc345fc9efaf7094669087ebb29"


def _load(name: str) -> Any:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def _sha(pdf: bytes) -> str:
    return hashlib.sha256(pdf).hexdigest()


def test_pre_review_template_v1_renders_to_the_committed_sha256() -> None:
    snapshot = PreReviewReportSnapshot.model_validate(_load("pre_review_v1"))
    pdf = render_pre_review_pdf(snapshot, template_version="1.0.0")
    assert _sha(pdf) == PRE_REVIEW_V1_SHA256
    assert _sha(render_pre_review_pdf(snapshot)) == PRE_REVIEW_V1_SHA256


def test_a_stored_v1_export_still_parses_and_renders_under_its_own_version() -> None:
    snapshot = parse_pre_review_snapshot(_load("pre_review_v1"), "1.0.0")
    assert type(snapshot) is PreReviewReportSnapshot
    assert _sha(render_pre_review_pdf(snapshot, template_version="1.0.0")) == PRE_REVIEW_V1_SHA256


def test_pre_review_template_v2_renders_to_the_committed_sha256() -> None:
    snapshot = parse_pre_review_snapshot(_load("pre_review_v2"), "2.0.0")
    assert isinstance(snapshot, PreReviewReportSnapshotV2)
    assert _sha(render_pre_review_pdf(snapshot, template_version="2.0.0")) == PRE_REVIEW_V2_SHA256
    assert _sha(render_pre_review_pdf(snapshot)) == PRE_REVIEW_V2_SHA256


def test_qualification_template_v1_renders_to_the_committed_sha256() -> None:
    snapshot = parse_qualification_snapshot(
        _load("qualification_v1"), QUALIFICATION_TEMPLATE_VERSION_V1
    )
    assert isinstance(snapshot, QualificationReportSnapshotV1)
    pdf = render_qualification_pdf(snapshot, template_version=QUALIFICATION_TEMPLATE_VERSION_V1)
    assert _sha(pdf) == QUALIFICATION_V1_SHA256


def test_qualification_template_v2_renders_to_the_committed_sha256() -> None:
    snapshot = parse_qualification_snapshot(
        _load("qualification_v2"), QUALIFICATION_TEMPLATE_VERSION
    )
    assert isinstance(snapshot, QualificationReportSnapshot)
    pdf = render_qualification_pdf(snapshot, template_version=QUALIFICATION_TEMPLATE_VERSION)
    assert _sha(pdf) == QUALIFICATION_V2_SHA256


def test_every_supported_template_version_has_a_golden_render() -> None:
    # A new template version without a golden here would be unguarded again.
    assert PRE_REVIEW_TEMPLATE_VERSIONS == ("1.0.0", TEMPLATE_VERSION) == ("1.0.0", "2.0.0")
    assert QUALIFICATION_TEMPLATE_VERSIONS == ("1.0.0", "2.0.0")


@pytest.mark.parametrize(
    "render",
    [
        lambda: render_pre_review_pdf(
            PreReviewReportSnapshot.model_validate(_load("pre_review_v1")), template_version="9.9.9"
        ),
        lambda: render_qualification_pdf(
            QualificationReportSnapshot.model_validate(_load("qualification_v2")),
            template_version="9.9.9",
        ),
    ],
)
def test_unknown_template_version_is_refused(render: Callable[[], bytes]) -> None:
    with pytest.raises(ValueError, match=r"9.9.9"):
        render()
