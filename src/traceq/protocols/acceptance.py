"""The AC validator: a drafted Acceptance Criterion is kept only when it is copied from a
verified citation (design section 9, "Drafted Test Steps").

The model proposes an AC and cites where it copied it from; code checks that the cited
document is one the model was given, that the quote is printed on the cited page and that the
quote states the AC value. Anything else leaves the AC empty and flagged "to be set by a
human", with the reason, so no limit is invented (ADR 0002: the LLM never sets an AC).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from traceq.traceability import Citation, Value
from traceq.traceability.citations import value_in_quote, verified

HUMAN = "to be set by a human"

Sources = Mapping[tuple[str, int], Sequence[str]]
"""The page texts of each document the model was given, by document and revision."""


@dataclass(frozen=True)
class Acceptance:
    value: Value | None
    citation: Citation | None
    """Verified: the quote is on the cited page and states ``value``."""
    flag: str | None
    """Why the AC is empty, for the human who sets it; ``None`` when it is sourced."""

    @property
    def sourced(self) -> bool:
        return self.flag is None


def _empty(reason: str) -> Acceptance:
    return Acceptance(None, None, f"{HUMAN}: {reason}")


def validate_acceptance(
    value: Value | None, citation: Citation | None, sources: Sources
) -> Acceptance:
    if value is None:
        return _empty("no acceptance criterion in the sources")
    if citation is None:
        return _empty("no source cited")
    pages = sources.get((citation.doc, citation.rev))
    if pages is None:
        return _empty("source not given")
    if not verified(citation, list(pages)):
        return _empty("quote not on the page")
    if not value_in_quote(value, citation.quote):
        return _empty("value not in the quote")
    return Acceptance(value, citation, None)
