"""Why a stored report export cannot be re-rendered (ADR 0007, ADR 0010).

A download re-renders the stored snapshot and checks the SHA-256 against the one stored with the
export. That only holds while the template version and the Typst compiler are the ones the export
was made with, so the checks here run first and name the cause in words.
"""

from __future__ import annotations

import hashlib
from collections.abc import Collection

from traceq.reports.pre_review import TYPST_VERSION


class ReportNotReproducible(Exception):
    """A stored export cannot be re-rendered to the PDF it was made with; the message says why."""


def check_render_inputs(
    *, template_version: str, typst_version: str, supported_templates: Collection[str]
) -> None:
    """Refuses a stored export whose template or Typst version this release cannot reproduce."""
    if template_version not in supported_templates:
        raise ReportNotReproducible(
            f"this export was made with template version {template_version}, which this release"
            f" no longer carries (it carries {', '.join(sorted(supported_templates))}), so its"
            " PDF cannot be re-rendered"
        )
    if typst_version != TYPST_VERSION:
        raise ReportNotReproducible(
            f"this export was made with Typst {typst_version} and the running Typst is"
            f" {TYPST_VERSION}, so its PDF cannot be re-rendered to the same bytes"
        )


def check_rendered_pdf(pdf_bytes: bytes, stored_sha256: str) -> None:
    """Refuses a re-render whose SHA-256 differs from the stored one: the integrity guarantee."""
    got = hashlib.sha256(pdf_bytes).hexdigest()
    if got != stored_sha256:
        raise ReportNotReproducible(
            f"the re-rendered PDF has SHA-256 {got}, not the stored {stored_sha256}, although the"
            " template and Typst versions match; the stored export cannot be verified"
        )
