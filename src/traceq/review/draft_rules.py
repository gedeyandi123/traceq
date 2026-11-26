"""Check Findings on a Protocol Draft (spec #196, "Rules"): layer Rule, over values read with a
verified citation. The LLM reads; it never judges a limit.

- ``ac_deviates_from_urs``: a Test Step's AC accepts a value the URS limit of a requirement
  the draft's traceability table traces it to rejects (``traceq.review.compare``). Cites the
  AC in the draft and the URS sentence.
- ``requirement_not_tested``: a traceability row none of whose Test Step ids the draft prints
  outside the traceability table. The table itself prints every planned id, so code searches
  the pages with the rows read taken out; a Test Step whose reading the citation check
  dropped is still printed, so it causes no finding. An id inside a longer one (``OQ-2`` in
  ``OQ-22``) is not that id. Cites the row.
- ``ac_outside_documented_capability`` (spec #375): a Test Step's AC demands more than the
  Datasheet states the Equipment can do: a maximum bound (more than the stated maximum), an
  operating span (a range reaching outside the stated span) or an accuracy floor (tighter than
  the stated accuracy). Cites the AC in the draft and the Datasheet row.
  ``ac_outside_documented_capability`` says what counts as a link and what is left out.
- ``unit_error`` (spec #375): a Test Step's AC prints the number of the URS limit it is traced to
  in a wrong unit: an SI prefix factor off (``18 cm`` for ``18 mm``) or another dimension
  (``300 m²/jam`` for ``300 m³/jam``). Equivalent units are not an error (``2 jam`` for
  ``120 menit``): the system's one unit table (``traceq.traceability.units``) converts them
  before the limit is compared. Where a unit error and ``ac_deviates_from_urs`` both apply to a
  Test Step, ``unit_error`` takes it. Cites the AC in the draft and the URS sentence.
- ``outdated_reference`` (spec #375): a Test Step cites, in its description, method, instrument or
  Acceptance Criterion, a document of the package's register at a revision lower than the
  register's current one. The read tags each citation's context (``normative``, ``revision
  history``, ``external standard``, ``unversioned``); only a ``normative`` one is judged, so a
  mention in revision history or supersession text, an external standard and a reference with no
  revision raise nothing. Code decides only the revision comparison. Cites the reference in the
  draft, by the sentence of the Test Step the reference stands in (not by the words the model
  quoted). A reference outside every Test Step (the title block) is not a finding: a finding
  sits on a Test Step or a table row.

A finding names its Test Step id (or, for a table row, the row's requirement id). Its detail
is written from the values as parsed, never from quote text, so a re-run whose quote differs
only in length gives the same finding.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from traceq.documents import normalise
from traceq.review.compare import UnitError
from traceq.review.draft import (
    Comparison,
    DraftReading,
    DraftRow,
    Reference,
    StepReading,
    TraceRow,
    outside_table,
    printed_at,
)
from traceq.review.printed import Limit, PrintedValue, Tolerance, read_printed
from traceq.traceability import Ambiguous, Citation
from traceq.traceability.citations import MAX_QUOTE
from traceq.traceability.coverage import comparable
from traceq.traceability.values import Number, Text

DraftType = Literal[
    "ac_deviates_from_urs",
    "requirement_not_tested",
    "ac_outside_documented_capability",
    "unit_error",
    "outdated_reference",
]

NOT_REVIEWED_LABEL = "not reviewed by a practitioner"
NOT_REVIEWED_TYPES: frozenset[str] = frozenset(
    {"ac_outside_documented_capability", "unit_error", "outdated_reference"}
)
"""Finding types no practitioner has reviewed (ADR 0010, amended 26 Nov 2026): each of their
findings carries ``NOT_REVIEWED_LABEL`` wherever it is shown."""


@dataclass(frozen=True)
class Datasheet:
    """A Datasheet of the corpus as the capability rule needs it: its printed text per page
    (page n is item n - 1) and its language, to read the printed values with."""

    doc: str
    rev: int
    language: str
    pages: tuple[str, ...]


@dataclass(frozen=True)
class DraftFinding:
    type: DraftType
    detail: str
    citations: tuple[Citation, ...]
    requirement: str
    test_step: str | None = None
    row: str | None = None
    """The traceability row's requirement id, for ``requirement_not_tested``."""
    ac: PrintedValue | None = None
    urs: PrintedValue | None = None
    capability: PrintedValue | None = None
    """The values compared, as parsed: the AC, the URS limit, or (for
    ``ac_outside_documented_capability``) the capability the Datasheet states."""

    @property
    def label(self) -> str | None:
        """``NOT_REVIEWED_LABEL`` when no practitioner has reviewed this type of finding."""
        return NOT_REVIEWED_LABEL if self.type in NOT_REVIEWED_TYPES else None


def _n(x: float) -> str:
    return f"{x:g}"


def _unit(v: Number | Limit) -> str:
    return f" {v.unit}" if v.unit else ""


def describe(v: PrintedValue) -> str:
    """A parsed value in words: ``at least 80 kN``, ``less than 0.8 µm``, ``20 to 30 mm``."""
    match v:
        case Number():
            return f"{_n(v.value)}{_unit(v)}"
        case Limit(min=lo, max=hi) if lo is not None and hi is not None:
            return f"{_n(lo)} to {_n(hi)}{_unit(v)}"
        case Limit(min=lo) if lo is not None:
            return f"{'more than' if v.min_exclusive else 'at least'} {_n(lo)}{_unit(v)}"
        case Limit():
            assert v.max is not None  # a Limit has at least one bound
            return f"{'less than' if v.max_exclusive else 'at most'} {_n(v.max)}{_unit(v)}"
        case Tolerance():
            return f"{_n(v.nominal)} {v.unit} ± {_n(v.tolerance)} {v.tolerance_unit}"
        case Text():
            return f"'{v.value}'"


def ac_deviates_from_urs(rows: list[DraftRow]) -> list[DraftFinding]:
    out: list[DraftFinding] = []
    for r in rows:
        for c in r.traced:
            if not c.deviates or c.unit_error is not None:
                continue  # a unit error takes the Test Step (spec #375)
            ac, urs = r.step.value, c.urs.value
            assert ac is not None and urs is not None and c.urs.citation is not None
            assert not isinstance(ac, Ambiguous)
            detail = (
                f"{r.step.id} accepts {describe(ac)}, which {c.urs.requirement} rejects:"
                f" it requires {describe(urs)}."
            )
            out.append(
                DraftFinding(
                    "ac_deviates_from_urs",
                    detail,
                    (r.step.citation, c.urs.citation),
                    c.urs.requirement,
                    test_step=r.step.id,
                    ac=ac,
                    urs=urs,
                )
            )
    return out


def _printed(step: str, texts: list[str]) -> bool:
    return any(printed_at(step, t) >= 0 for t in texts)


def requirement_not_tested(reading: DraftReading) -> list[DraftFinding]:
    texts = outside_table(reading)
    read = {s.id for s in reading.steps}
    by_requirement: dict[str, list[TraceRow]] = {}
    for r in reading.rows:
        by_requirement.setdefault(r.requirement, []).append(r)
    out: list[DraftFinding] = []
    for req, rows in by_requirement.items():
        steps = list(dict.fromkeys(s for r in rows for s in r.steps))
        if any(s in read or _printed(s, texts) for s in steps):
            continue
        detail = (
            f"The traceability table lists {req} under {', '.join(steps)}, but the draft has"
            " no such Test Step: the requirement is not tested."
        )
        cites = tuple(dict.fromkeys(r.citation for r in rows))
        out.append(DraftFinding("requirement_not_tested", detail, cites, req, row=req))
    return out


# --- ac_outside_documented_capability ---------------------------------------------------------

_UTILITIES = re.compile(
    r"^(?:\d+(?:\.\d+)*[.)]?\s+)?(?:utilities|utility|utilitas)(?:\s+(?:and|dan|&)\s+\w+)?$",
    re.IGNORECASE,
)
"""A line that is a Utilities heading: ``Utilities``, ``5. Utilitas dan lingkungan``."""
_ACCURACY = re.compile(r"accuracy|akurasi", re.IGNORECASE)
_MAXIMUM = re.compile(r"maximum|maksimum|maksimal|\bmax\b|\bmaks\b", re.IGNORECASE)

Capability = Literal["maximum", "span", "accuracy"]


def _bound(v: PrintedValue) -> float | None:
    """The single number a stated maximum or accuracy prints: ``100 kN``, ``at most 1 %``."""
    match v:
        case Number():
            return v.value
        case Limit(min=None, max=hi) if hi is not None:
            return hi
        case _:
            return None


def _kind(name: str, value: PrintedValue) -> Capability | None:
    """What the Datasheet row states, from its name and the value it prints: an accuracy and a
    maximum say so in their name, a span is a two-sided range. Any other row states no
    capability the rule can type."""
    if _ACCURACY.search(name):
        return "accuracy" if _bound(value) is not None else None
    if isinstance(value, Limit) and value.min is not None and value.max is not None:
        return "span"
    if _MAXIMUM.search(name) and _bound(value) is not None:
        return "maximum"
    return None


def _outside_maximum(ac: Number | Limit, top: float) -> bool:
    """The AC demands a value above the stated maximum: a number, a lower bound, or the upper
    end of a range. An upper limit alone demands nothing."""
    if isinstance(ac, Number):
        return ac.value > top
    if ac.max is not None and ac.min is not None:
        return ac.max > top
    if ac.min is not None:
        return ac.min > top or (ac.min == top and ac.min_exclusive)
    return False


def _outside_span(ac: Number | Limit, span: Limit) -> bool:
    """The AC reaches outside the stated span: a number or a range beyond either end, a lower
    bound above the span, or an upper bound below it."""
    assert span.min is not None and span.max is not None
    lo, hi = span.min, span.max
    if isinstance(ac, Number):
        return ac.value < lo or ac.value > hi
    if ac.min is not None and ac.max is not None:
        return ac.min < lo or ac.max > hi
    if ac.min is not None:
        return ac.min > hi or (ac.min == hi and ac.min_exclusive)
    assert ac.max is not None
    return ac.max < lo or (ac.max == lo and ac.max_exclusive)


def _tighter(ac: Number | Limit, floor: float) -> bool:
    """The AC allows an error smaller than the stated accuracy (a limit ``at most ± a``)."""
    if not isinstance(ac, Limit) or ac.min is not None or ac.max is None:
        return False
    return ac.max < floor or (ac.max == floor and ac.max_exclusive)


def _under_utilities(sheet: Datasheet, page: int, name: str) -> bool:
    """Whether the row ``name`` of ``page`` sits under a Utilities heading, by the page text: a
    Utilities heading line before it on the page, or on an earlier page. Conservative: once
    the heading is seen every later row of the document is left out (the page does not tell
    where a section ends), and a name the page prints twice is under it when either place is."""
    needle = normalise(name)
    for n, text in enumerate(sheet.pages[:page], 1):
        flat, headings = "", list[int]()
        for line in (normalise(x) for x in text.splitlines()):
            if not line:
                continue
            if _UTILITIES.match(line):
                headings.append(len(flat))
            flat = f"{flat} {line}" if flat else line
        if n < page:
            if headings:
                return True
            continue
        starts = [m.start() for m in re.finditer(re.escape(needle), flat)]
        return any(h <= s for h in headings for s in starts)
    return False


@dataclass(frozen=True)
class _Stated:
    """A capability the Datasheet states, as read from the row's printed text."""

    sheet: Datasheet
    name: str
    citation: Citation
    value: PrintedValue


def _stated(c: Comparison, sheets: dict[tuple[str, int], Datasheet]) -> list[_Stated]:
    """The Datasheet rows the requirement is linked to whose name the page holds, outside
    Utilities, with the value read from the printed text."""
    out: list[_Stated] = []
    for comparator in c.comparators:
        sheet = sheets.get((comparator.doc, comparator.rev))
        if comparator.kind != "design" or sheet is None:
            continue
        for fact in comparator.facts:
            page = fact.citation.page
            if not 1 <= page <= len(sheet.pages) or not normalise(fact.name):
                continue
            if normalise(fact.name) not in normalise(sheet.pages[page - 1]):
                continue  # the name is the model's: it must be on the page its citation names
            if _under_utilities(sheet, page, fact.name):
                continue
            value = read_printed(fact.printed, sheet.language)
            if isinstance(value, Ambiguous) or value is None or isinstance(value, Text):
                continue
            out.append(_Stated(sheet, fact.name, fact.citation, value))
    return out


def _capability_detail(step: str, ac: PrintedValue, s: _Stated, kind: Capability) -> str:
    where = {
        "maximum": f"above the maximum {describe(s.value)}",
        "span": f"outside the span {describe(s.value)}",
        "accuracy": f"tighter than the {describe(s.value)} accuracy",
    }[kind]
    return (
        f"{step} requires {describe(ac)}, {where} the Datasheet {s.sheet.doc} states:"
        " the limit may not be reachable."
    )


def ac_outside_documented_capability(
    rows: list[DraftRow], datasheets: Sequence[Datasheet]
) -> list[DraftFinding]:
    """A Test Step whose AC demands more than the Datasheet in the package states. It fires
    only where the requirement the draft's table traces the step to is linked, by the Coverage
    the system already read with a verified citation, to a Datasheet row: with no such link it
    raises nothing. FAT and SAT results, certificates and utility supply rows are not
    comparators (ADR 0010, Limits).

    The value is parsed from the row's printed text, not from the stored fact (whose unit
    loses the full-scale qualifier), and only where the units compare (``coverage.comparable``):
    a prefix or dimension slip is ``unit_error``'s. The row's name is the model's, so it must
    be on the page its citation names; a row under a Utilities heading is excluded by the page
    text. A step whose header names another requirement than the table lists is not judged."""
    sheets = {(d.doc, d.rev): d for d in datasheets}
    out: list[DraftFinding] = []
    for r in rows:
        ac = r.step.value
        if ac is None or isinstance(ac, Ambiguous | Tolerance | Text):
            continue
        if any(q not in {c.urs.requirement for c in r.traced} for q in r.step.requirements):
            continue
        seen: set[tuple[str, int, str]] = set()
        for c in r.traced:
            for s in _stated(c, sheets):
                key = (s.sheet.doc, s.sheet.rev, s.name)
                kind, top = _kind(s.name, s.value), _bound(s.value)
                if key in seen or kind is None or not comparable(_as_number(s.value), ac):
                    continue
                if kind == "maximum":
                    assert top is not None
                    outside = _outside_maximum(ac, top)
                elif kind == "span":
                    assert isinstance(s.value, Limit)
                    outside = _outside_span(ac, s.value)
                else:
                    assert top is not None
                    outside = _tighter(ac, top)
                if not outside:
                    continue
                seen.add(key)
                out.append(
                    DraftFinding(
                        "ac_outside_documented_capability",
                        _capability_detail(r.step.id, ac, s, kind),
                        (r.step.citation, s.citation),
                        c.urs.requirement,
                        test_step=r.step.id,
                        ac=ac,
                        capability=s.value,
                    )
                )
    return out


# --- unit_error --------------------------------------------------------------------------------


def _unit_detail(
    step: str, requirement: str, ac: PrintedValue, urs: PrintedValue, e: UnitError
) -> str:
    how = (
        f"the unit is off by a factor of {e.factor}"
        if e.kind == "prefix"
        else "the unit has other dimensions"
    )
    return (
        f"{step} prints {describe(ac)} where {requirement} says {describe(urs)}: the number is"
        f" the URS number and {how}."
    )


def unit_error(rows: list[DraftRow]) -> list[DraftFinding]:
    """A Test Step whose AC prints the number of its URS limit in a unit off by a power of ten
    or of another dimension (``traceq.review.compare``); equivalent units raise nothing."""
    out: list[DraftFinding] = []
    for r in rows:
        for c in r.traced:
            if c.unit_error is None:
                continue
            ac, urs = r.step.value, c.urs.value
            assert ac is not None and urs is not None and c.urs.citation is not None
            assert not isinstance(ac, Ambiguous)
            out.append(
                DraftFinding(
                    "unit_error",
                    _unit_detail(r.step.id, c.urs.requirement, ac, urs, c.unit_error),
                    (r.step.citation, c.urs.citation),
                    c.urs.requirement,
                    test_step=r.step.id,
                    ac=ac,
                    urs=urs,
                )
            )
    return out


# --- outdated_reference ------------------------------------------------------------------------

_NOT_ALNUM = re.compile(r"[\W_]+")


def _canonical(document: str) -> str:
    """A document id as compared: case, spaces and punctuation do not tell two ids apart
    (``SOP-017`` and ``sop 017``)."""
    return _NOT_ALNUM.sub("", normalise(document)).casefold()


def _fields(step: StepReading) -> tuple[tuple[str, str, int], ...]:
    """The text of a Test Step the draft prints, by field, with its page: where a reference to
    another document can sit."""
    out = [
        (name, f.text, f.citation.page)
        for name, f in (
            ("description", step.description),
            ("method", step.method),
            ("instrument", step.instrument),
        )
        if f is not None
    ]
    out.append(("acceptance criterion", normalise(step.citation.quote), step.citation.page))
    return tuple(out)


_SENTENCE_END = re.compile(r"(?<![Rr]ev)(?<![Nn]o)[.;!?](?=\s|$)")
"""Where a sentence of a Test Step's text ends; ``Rev.`` and ``No.`` are abbreviations."""


def _sentence(text: str, quote: str) -> str:
    """The sentence(s) of ``text`` that hold ``quote``, so that a reference is cited by the
    sentence it stands in, never by the few words the model chose to quote (the reviewer reads
    the sentence; a citation's length does not decide whether it names the place). Fallback:
    ``quote`` itself, as the model gave it, when it is not in ``text`` or the sentence would
    pass ``MAX_QUOTE`` (a citation may not be longer); a scorer that matches by location may
    then miss the finding, which is the price of the cap (tested)."""
    at = text.find(quote)
    if at < 0:
        return quote
    ends = [m.end() for m in _SENTENCE_END.finditer(text)]
    start = max((e for e in ends if e <= at), default=0)
    end = min((e for e in ends if e >= at + len(quote)), default=len(text))
    sentence = text[start:end].strip()
    return sentence if quote in sentence and len(sentence) <= MAX_QUOTE else quote


def _requirement(row: DraftRow) -> str:
    """The requirement the draft's table lists the Test Step under, else the one it names."""
    if row.traced:
        return row.traced[0].urs.requirement
    return row.step.requirements[0] if row.step.requirements else ""


def outdated_reference(
    reading: DraftReading, rows: list[DraftRow], register: Mapping[str, int]
) -> list[DraftFinding]:
    """A Test Step that cites, as a normative reference, a document of the register at a
    revision lower than the register's current one. ``register``: the current revision of
    every document of the package's corpus, by document id. The read tags the context of each
    reference and code only compares revisions: a reference that is not ``normative``, one
    that prints no number, one to a document the register does not hold, and one at the
    current or a higher revision raise nothing. A reference sits on the Test Step whose
    description, method, instrument or Acceptance Criterion holds its quote."""
    current = {_canonical(doc): (doc, rev) for doc, rev in register.items()}
    stale: list[tuple[Reference, str, int]] = []
    seen: set[tuple[str, int, str, str]] = set()
    for ref in reading.references:
        if ref.context != "normative" or ref.revision is None:
            continue
        known = current.get(_canonical(ref.document))
        key = (
            ref.citation.quote,
            ref.citation.page,
            _canonical(ref.document),
            ref.printed_revision,
        )
        if known is None or ref.revision >= known[1] or key in seen:
            continue
        seen.add(key)
        stale.append((ref, *known))
    out: list[DraftFinding] = []
    for r in rows:
        for ref, doc, rev in stale:
            quote = normalise(ref.citation.quote)
            held = next(
                (
                    (name, text)
                    for name, text, page in _fields(r.step)
                    if page == ref.citation.page and quote in text
                ),
                None,
            )
            if held is None:
                continue
            where, text = held
            cited = Citation(
                ref.citation.doc,
                ref.citation.rev,
                ref.citation.page,
                _sentence(text, quote),
            )
            detail = (
                f"{r.step.id} cites {doc} Rev. {ref.printed_revision} in its {where}, but the"
                f" register holds {doc} at Rev. {rev}: the citation may be superseded."
            )
            out.append(
                DraftFinding(
                    "outdated_reference",
                    detail,
                    (cited,),
                    _requirement(r),
                    test_step=r.step.id,
                )
            )
    return out


def _as_number(v: PrintedValue) -> Number | Limit:
    assert isinstance(v, Number | Limit)
    return v


def draft_findings(
    reading: DraftReading,
    rows: list[DraftRow],
    datasheets: Sequence[Datasheet] = (),
    register: Mapping[str, int] | None = None,
) -> list[DraftFinding]:
    """Every Check Finding on the draft: ``ac_deviates_from_urs`` by Test Step in draft order,
    then ``requirement_not_tested`` by table row, then the types added since (spec #375), each
    by Test Step in draft order, so the numbering of the older findings never moves.
    ``datasheets``: the corpus's Datasheets, for ``ac_outside_documented_capability``.
    ``register``: the current revision of every document of the corpus, for
    ``outdated_reference`` (none: the rule has nothing to compare with)."""
    return [
        *ac_deviates_from_urs(rows),
        *requirement_not_tested(reading),
        *ac_outside_documented_capability(rows, datasheets),
        *unit_error(rows),
        *outdated_reference(reading, rows, register or {}),
    ]
