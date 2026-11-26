"""Why a stored report export cannot be re-rendered (ADR 0007, ADR 0010).

A download re-renders the stored snapshot and checks the SHA-256 against the one stored with the
export; that check is the integrity guarantee and always runs. Only a template version this
release no longer carries is refused before rendering, because it cannot be rendered at all. A
Typst version that differs from the running one is not a refusal by itself (a compiler upgrade
may render the same bytes): it is named as the likely cause when the SHA-256 then differs.
"""

from __future__ import annotations

import hashlib
from collections.abc import Collection

from traceq.reports.pre_review import TYPST_VERSION


class ReportNotReproducible(Exception):
    """A stored export cannot be re-rendered to the PDF it was made with; the message says why."""


def check_template_supported(template_version: str, supported_templates: Collection[str]) -> None:
    """Refuses a stored export whose template version this release no longer carries."""
    if template_version not in supported_templates:
        raise ReportNotReproducible(
            f"this export was made with template version {template_version}, which this release"
            f" no longer carries (it carries {', '.join(sorted(supported_templates))}), so its"
            " PDF cannot be re-rendered"
        )


def check_rendered_pdf(pdf_bytes: bytes, stored_sha256: str, *, stored_typst_version: str) -> None:
    """Refuses a re-render whose SHA-256 differs from the stored one: the integrity guarantee.

    When the Typst version stored with the export is not the running one, the message names both
    as the likely cause."""
    got = hashlib.sha256(pdf_bytes).hexdigest()
    if got == stored_sha256:
        return
    if stored_typst_version != TYPST_VERSION:
        raise ReportNotReproducible(
            f"the re-rendered PDF has SHA-256 {got}, not the stored {stored_sha256}; the export"
            f" was made with Typst {stored_typst_version} and the running Typst is"
            f" {TYPST_VERSION}, which is the likely cause"
        )
    raise ReportNotReproducible(
        f"the re-rendered PDF has SHA-256 {got}, not the stored {stored_sha256}, although the"
        " template and Typst versions match; the stored export cannot be verified"
    )
