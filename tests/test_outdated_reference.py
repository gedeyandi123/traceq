"""Rule ``outdated_reference`` (spec #375, ticket S2c): the read tags the context of every
reference to another document; code decides only the revision comparison against the package's
register. Facts are built as the reader keeps them (verified citations); the rule never sees a
model. The package's own Clean Traps are in ``tests/test_outdated_reference_run.py``."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

import pytest

from traceq.documents import CorpusDocument, Page
from traceq.review.draft import (
    DraftReading,
    FieldReading,
    Reference,
    ReferenceContext,
    StepReading,
    TraceRow,
    draft_rows,
)
from traceq.review.draft_rules import NOT_REVIEWED_LABEL, DraftFinding, draft_findings
from traceq.review.printed import read_printed
from traceq.traceability import Citation, Requirement, Traceability

DOC = CorpusDocument(
    "OQ-XY100", 0, "oq_protocol", "born_digital", "id", Path("draft.pdf"), "d" * 64
)
REGISTER = {"SOP-017": 3, "VMP-002": 5, "URS-XY100": 1}
METHOD = "Jalankan mesin tanpa produk sesuai SOP-017 Rev. 2."
STALE = "sesuai SOP-017 Rev. 2."


def _cite(page: int, quote: str) -> Citation:
    return Citation(DOC.doc_id, 0, page, quote)


def _field(page: int, text: str) -> FieldReading:
    return FieldReading(text, _cite(page, text))


def _step(sid: str = "OQ-01", req: str = "URS-XY100-004", **fields: FieldReading) -> StepReading:
    ac = "maks. 80 dB"
    return StepReading(
        sid,
        (req,),
        ac,
        read_printed(ac, "id"),
        _cite(1, f"Kriteria penerimaan {ac}"),
        **fields,
    )


def _ref(
    document: str = "SOP-017",
    revision: str = "2",
    context: ReferenceContext = "normative",
    quote: str = STALE,
    page: int = 1,
) -> Reference:
    number = revision.strip()[:1]
    return Reference(
        document,
        revision,
        int(number) if number.isdigit() else None,
        context,
        _cite(page, quote),
    )


def _judge(
    steps: Sequence[StepReading],
    refs: Sequence[Reference],
    register: dict[str, int] | None = None,
) -> list[DraftFinding]:
    rows = [
        TraceRow(s.requirements[0], (s.id,), _cite(2, f"{s.requirements[0]} {s.id}")) for s in steps
    ]
    reading = DraftReading(DOC, (Page(1, ""), Page(2, "")), list(steps), rows)
    reading.references.extend(refs)
    urs = Requirement(
        "URS-XY100-004",
        "Bising maksimal 80 dB.",
        Citation("URS-XY100", 1, 1, "URS-XY100-004 Bising maksimal 80 dB."),
        True,
    )
    traced = draft_rows(reading, Traceability(requirements=[urs]), "id")
    found = draft_findings(reading, traced, (), REGISTER if register is None else register)
    return [f for f in found if f.type == "outdated_reference"]


def test_a_normative_citation_of_a_lower_revision_than_the_register_is_a_finding() -> None:
    (f,) = _judge([_step(method=_field(1, METHOD))], [_ref()])
    assert (f.type, f.test_step, f.row, f.requirement) == (
        "outdated_reference",
        "OQ-01",
        None,
        "URS-XY100-004",
    )
    assert f.detail == (
        "OQ-01 cites SOP-017 Rev. 2 in its method, but the register holds SOP-017 at Rev. 3:"
        " the citation may be superseded."
    )
    assert f.citations == (_cite(1, METHOD),), "the sentence the reference stands in"
    assert f.label == NOT_REVIEWED_LABEL


@pytest.mark.parametrize(
    ("text", "quote", "sentence"),
    [
        (
            "Atur mesin. Ikuti SOP-017 Rev. 2. Catat hasil.",
            "SOP-017 Rev. 2",
            "Ikuti SOP-017 Rev. 2.",
        ),
        ("Atur mesin. Ikuti SOP-017 Rev. 2. Catat hasil.", "Rev. 2.", "Ikuti SOP-017 Rev. 2."),
        (
            "Ikuti SOP-017 Rev. 2 dan VMP-002 Rev. 4.",
            "VMP-002 Rev. 4",
            "Ikuti SOP-017 Rev. 2 dan VMP-002 Rev. 4.",
        ),
        ("Ikuti SOP-017 Rev. 2; catat hasil.", "SOP-017 Rev. 2", "Ikuti SOP-017 Rev. 2;"),
        ("Ikuti SOP-017 Rev. 2", "SOP-017 Rev. 2", "Ikuti SOP-017 Rev. 2"),
        (f"{'x' * 190} SOP-017 Rev. 2 dan seterusnya.", "SOP-017 Rev. 2", "SOP-017 Rev. 2"),
    ],
)
def test_the_citation_is_the_sentence_of_the_reference_not_the_models_few_words(
    text: str, quote: str, sentence: str
) -> None:
    step = _step(method=_field(1, text))
    (f,) = _judge([step], [_ref(quote=quote)])
    assert f.citations == (_cite(1, sentence),)


@pytest.mark.parametrize("context", ["revision_history", "external_standard", "unversioned"])
def test_only_a_normative_citation_is_judged(context: ReferenceContext) -> None:
    """History text, external standards and unversioned references are Clean Traps: the tag is
    part of the read, code does not second-guess it."""
    assert _judge([_step(method=_field(1, METHOD))], [_ref(context=context)]) == []


@pytest.mark.parametrize(
    ("document", "revision", "expected"),
    [
        ("SOP-017", "3", False),  # the current revision
        ("SOP-017", "4", False),  # newer than the register: not outdated
        ("SOP-017", "1", True),
        ("SOP-017", "", False),  # no revision printed
        ("SOP-017", "B", False),  # a letter is not a number to compare
        ("SOP-099", "1", False),  # not in the register
        ("sop 017", "2", True),  # case and punctuation do not tell an id apart
        ("SOP017", "2", True),
        ("SOP-017-A", "2", False),  # another id
        ("VMP-002", "4", True),
    ],
)
def test_code_decides_only_the_revision_comparison(
    document: str, revision: str, expected: bool
) -> None:
    quote = f"sesuai {document} Rev. {revision}".rstrip()
    ref = _ref(document, revision, quote=quote)
    step = _step(method=_field(1, f"Jalankan mesin {quote}"))
    assert bool(_judge([step], [ref])) is expected


def test_no_register_no_finding() -> None:
    assert _judge([_step(method=_field(1, METHOD))], [_ref()], {}) == []


@pytest.mark.parametrize("name", ["description", "method", "instrument"])
def test_the_reference_sits_on_the_field_that_holds_its_quote(name: str) -> None:
    step = replace(_step(), **{name: _field(1, METHOD)})
    (f,) = _judge([step], [_ref()])
    assert f"in its {name}," in f.detail


def test_a_reference_in_the_acceptance_criterion_is_a_finding_of_that_step() -> None:
    step = StepReading(
        "OQ-01",
        ("URS-XY100-004",),
        "maks. 80 dB",
        read_printed("maks. 80 dB", "id"),
        _cite(1, "Kriteria penerimaan maks. 80 dB sesuai SOP-017 Rev. 2."),
    )
    (f,) = _judge([step], [_ref()])
    assert "in its acceptance criterion," in f.detail


def test_a_reference_outside_every_test_step_is_not_a_finding() -> None:
    """A finding sits on a Test Step or a table row; the title block is neither."""
    other_page = _field(2, METHOD)
    assert _judge([_step(method=_field(1, "Jalankan mesin."))], [_ref()]) == []
    assert _judge([_step(method=other_page)], [_ref()]) == []


def test_the_reference_belongs_to_the_step_that_holds_it() -> None:
    steps = [
        _step("OQ-01", method=_field(1, "Jalankan mesin.")),
        _step("OQ-02", method=_field(1, METHOD)),
    ]
    assert [f.test_step for f in _judge(steps, [_ref()])] == ["OQ-02"]


def test_one_finding_per_stale_reference_of_a_step_and_a_repeated_mention_counts_once() -> None:
    text = "Ikuti SOP-017 Rev. 1 lalu VMP-002 Rev. 4 dan SOP-017 Rev. 1."
    refs = [
        _ref(quote="Ikuti SOP-017 Rev. 1", revision="1"),
        _ref("VMP-002", "4", quote="VMP-002 Rev. 4"),
        _ref(quote="Ikuti SOP-017 Rev. 1", revision="1"),
    ]
    found = _judge([_step(method=_field(1, text))], refs)
    assert [f.detail.split(" in its")[0] for f in found] == [
        "OQ-01 cites SOP-017 Rev. 1",
        "OQ-01 cites VMP-002 Rev. 4",
    ]


def test_a_finding_without_a_table_row_uses_the_requirement_the_step_names() -> None:
    step = _step(method=_field(1, METHOD))
    reading = DraftReading(DOC, (Page(1, ""),), [step], [])
    reading.references.append(_ref())
    rows = draft_rows(reading, Traceability(requirements=[]), "id")
    (f,) = [
        x for x in draft_findings(reading, rows, (), REGISTER) if x.type == "outdated_reference"
    ]
    assert (f.test_step, f.requirement) == ("OQ-01", "URS-XY100-004")


def test_the_new_findings_come_after_every_older_one() -> None:
    step = _step(method=_field(1, METHOD))
    rows = [TraceRow("URS-XY100-004", ("OQ-01",), _cite(2, "URS-XY100-004 OQ-01"))]
    reading = DraftReading(DOC, (Page(1, ""), Page(2, "")), [step], rows)
    reading.references.append(_ref())
    urs = Requirement(
        "URS-XY100-004",
        "Bising maksimal 70 dB.",
        Citation("URS-XY100", 1, 1, "URS-XY100-004 Bising maksimal 70 dB."),
        True,
    )
    traced = draft_rows(reading, Traceability(requirements=[urs]), "id")
    types = [f.type for f in draft_findings(reading, traced, (), REGISTER)]
    assert types == ["ac_deviates_from_urs", "outdated_reference"]
