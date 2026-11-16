"""``completeness.json``: the URS completeness check of a run (``traceability.completeness``).

The shape is ``traceq.runs.schemas.Completeness``, which the API serves.
"""

from __future__ import annotations

from traceq.runs.schemas import Completeness, MissedNumber, UnquotedText, UrsCompleteness
from traceq.traceability import Traceability

COMPLETENESS_FILE = "completeness.json"


def completeness(t: Traceability) -> Completeness:
    return Completeness(
        urs=tuple(
            UrsCompleteness(
                doc=c.doc,
                rev=c.rev,
                numbers=c.numbers,
                found=c.found,
                missed=tuple(MissedNumber(number=m.number, page=m.page) for m in c.missed),
                unquoted=tuple(UnquotedText(page=u.page, text=u.text) for u in c.unquoted),
            )
            for c in t.completeness
        )
    )
