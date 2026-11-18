"""Reading a Protocol Draft (spec #196, ticket #207): the limit parser for the formats a draft
prints and a URS states, the citation check on what the model reads, and the URS limit read
from the requirement's verified citation."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from traceq.ai import Request, Response
from traceq.documents import CorpusDocument, Page, ReviewPackage
from traceq.review.draft import (
    DRAFT_PROMPT,
    DraftReading,
    StepReading,
    draft_rows,
    read_draft,
    urs_limit,
)
from traceq.review.limits import outside
from traceq.review.printed import Limit, Tolerance, read_printed
from traceq.traceability import Ambiguous, Citation, Requirement, Traceability
from traceq.traceability.values import Number, Text

# --- The limit parser -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("printed", "value"),
    [
        ("minimal 100 kN", Limit(min=100, unit="kN")),
        ("Minimal 100 kN", Limit(min=100, unit="kN")),
        ("min. 4 bar", Limit(min=4, unit="bar")),
        ("tidak kurang dari 36 stasiun", Limit(min=36, unit="stasiun")),
        ("≥ 120.000 tablet/jam", Limit(min=120000, unit="tablet/jam")),
        ("minimal 300 m³/jam", Limit(min=300, unit="m³/jam")),
        ("> 5 kN", Limit(min=5, min_exclusive=True, unit="kN")),
        ("lebih dari 5 kN", Limit(min=5, min_exclusive=True, unit="kN")),
        ("maks. 25 mm", Limit(max=25, unit="mm")),
        ("maks. 17,5 mm", Limit(max=17.5, unit="mm")),
        ("maksimal 85 dBA", Limit(max=85, unit="dBA")),
        ("maks. 60 dB(A)", Limit(max=60, unit="dB(A)")),
        ("tidak lebih dari 2 jam", Limit(max=2, unit="jam")),
        ("≤ 25 mm", Limit(max=25, unit="mm")),
        ("Ra maks. 0,8 µm", Limit(max=0.8, unit="µm")),
        ("Ra < 0,8 µm", Limit(max=0.8, max_exclusive=True, unit="µm")),
        ("kurang dari 0,8 µm", Limit(max=0.8, max_exclusive=True, unit="µm")),
        ("tinggi maks. 3.200 mm", Limit(max=3200, unit="mm")),
        ("maks. ± 2 % FS", Limit(max=2, unit="% FS")),
        ("± 1 % FS", Limit(max=1, unit="% FS")),
        ("20 s/d 70 rpm", Limit(min=20, max=70, unit="rpm")),
        ("10–60 rpm", Limit(min=10, max=60, unit="rpm")),
        ("6 - 7 bar", Limit(min=6, max=7, unit="bar")),
        ("18 sampai 25 °C", Limit(min=18, max=25, unit="°C")),
        (
            "380 V ± 10 %, 3 fase",
            Tolerance(nominal=380, tolerance=10, tolerance_unit="%", unit="V"),
        ),
        ("36 stasiun punch", Number(value=36, unit="stasiun")),
        ("400 V, 3 fase", Number(value=400, unit="V")),
        ("Mesin berhenti saat pintu dibuka", Text(value="Mesin berhenti saat pintu dibuka")),
    ],
)
def test_parser_reads_each_format_a_draft_prints(printed: str, value: object) -> None:
    assert read_printed(printed, "id") == value


@pytest.mark.parametrize(
    ("printed", "value"),
    [
        ("URS-XY100-004 Ya Gaya tekan yang dapat dicapai minimal 80 kN.", Limit(min=80, unit="kN")),
        ("URS-XY100-006 Tidak Diameter tablet maksimal 16 mm.", Limit(max=16, unit="mm")),
        (
            "URS-XY100-002 Ya Kecepatan dapat diatur pada rentang 5–40 rpm.",
            Limit(min=5, max=40, unit="rpm"),
        ),
        ("URS-XY100-001 Tidak Mesin memiliki 24 stasiun punch.", Number(value=24, unit="stasiun")),
    ],
)
def test_parser_reads_a_limit_inside_a_urs_sentence(printed: str, value: object) -> None:
    rid = printed.split()[0]
    assert read_printed(printed, "id", ignore=(rid,)) == value


def test_parser_never_guesses_a_number_that_reads_two_ways() -> None:
    assert read_printed("maks. 1.500 rpm", "en") == Ambiguous((1500.0, 1.5))
    assert read_printed("minimal 1,500 kN", "id") == Ambiguous((1500.0, 1.5))
    assert read_printed("minimal 120.000 tablet/jam", "id") == Limit(min=120000, unit="tablet/jam")


@pytest.mark.parametrize("printed", ["maks. 20–30 mm", "70–20 rpm", "minimal ± 2 %"])
def test_parser_leaves_a_form_it_does_not_know_unread(printed: str) -> None:
    assert read_printed(printed, "id") is None


def test_digits_in_ids_are_not_a_number() -> None:
    assert read_printed("Lihat OQ-05 dan URS-XY100-003", "id") == Text(
        value="Lihat OQ-05 dan URS-XY100-003"
    )


@pytest.mark.parametrize(
    ("acceptance", "observed", "out"),
    [
        ("≥ 100 kN", "96 kN", True),
        ("≥ 100 kN", "104 kN", False),
        ("20–60 rpm", "65 rpm", True),
        ("≤ 0.5 % FS", "0.4 % FS", False),
        ("minimal 100 kN", "96 kN", None),  # the record rule's parser is unchanged
    ],
)
def test_out_of_limit_rule_keeps_todays_formats(
    acceptance: str, observed: str, out: bool | None
) -> None:
    assert outside(acceptance, observed, "en") is out


# --- Reading the draft ----------------------------------------------------------------

DOC = CorpusDocument(
    "OQ-XY100", 0, "oq_protocol", "born_digital", "id", Path("draft.pdf"), "d" * 64
)
PAGES = [
    Page(
        1,
        "Langkah uji OQ-01\nPersyaratan URS-XY100-004\nKriteria penerimaan minimal 75 kN\n"
        "Langkah uji OQ-02\nPersyaratan URS-XY100-006\nKriteria penerimaan maks. 1.500 mm\n"
        "Langkah uji OQ-03\nPersyaratan URS-XY100-007\nKriteria penerimaan Mesin berhenti",
    ),
    Page(
        2,
        "Matriks ketertelusuran\nURS-XY100-004 Gaya tekan OQ-01\n"
        "URS-XY100-006 Diameter OQ-02\nURS-XY100-009 Kebisingan OQ-09",
    ),
]


def _answer(steps: list[dict[str, Any]], rows: list[dict[str, Any]]) -> str:
    return json.dumps({"test_steps": steps, "trace_rows": rows})


ANSWERS = [
    _answer(
        [
            {
                "id": "OQ-01",
                "requirements": ["URS-XY100-004"],
                "acceptance": "minimal 75 kN",
                "quote": "Kriteria penerimaan minimal 75 kN",
            },
            {
                "id": "OQ-02",
                "requirements": ["URS-XY100-006"],
                "acceptance": "maks. 1.500 mm",
                "quote": "maks. 1.500 mm",
            },
            # the quote is not on the page: dropped
            {
                "id": "OQ-03",
                "requirements": ["URS-XY100-007"],
                "acceptance": "Mesin berhenti segera",
                "quote": "Mesin berhenti segera",
            },
            # the id is not printed on the page: dropped
            {
                "id": "OQ-04",
                "requirements": [],
                "acceptance": "minimal 75 kN",
                "quote": "minimal 75 kN",
            },
        ],
        [],
    ),
    _answer(
        [],
        [
            {
                "requirement": "URS-XY100-004",
                "test_steps": ["OQ-01"],
                "quote": "URS-XY100-004 Gaya tekan OQ-01",
            },
            {
                "requirement": "URS-XY100-009",
                "test_steps": ["OQ-09"],
                "quote": "URS-XY100-009 Kebisingan OQ-09",
            },
            # the quote does not hold the step id: dropped
            {
                "requirement": "URS-XY100-006",
                "test_steps": ["OQ-05"],
                "quote": "URS-XY100-006 Diameter OQ-02",
            },
        ],
    ),
]


class _Fake:
    model = "fake"

    def __init__(self, answers: Sequence[str]) -> None:
        self.answers = list(answers)
        self.requests: list[Request] = []

    def complete(self, requests: Sequence[Request]) -> list[Response]:
        self.requests += requests
        return [Response(a, self.model, 10, 5) for a in self.answers[: len(requests)]]


@pytest.fixture
def reading() -> tuple[DraftReading, _Fake]:
    llm = _Fake(ANSWERS)
    return read_draft(DOC, PAGES, llm), llm


def test_one_call_per_page_with_the_draft_prompt(reading: tuple[DraftReading, _Fake]) -> None:
    _, llm = reading
    assert [r.prompt.name for r in llm.requests] == ["protocol_draft"] * 2
    assert all(r.doc_sha256 == DOC.sha256 for r in llm.requests)
    assert "page 2" in llm.requests[1].user and PAGES[1].text in llm.requests[1].user


def test_only_readings_whose_quote_passes_the_check_are_kept(
    reading: tuple[DraftReading, _Fake],
) -> None:
    r, _ = reading
    assert [s.id for s in r.steps] == ["OQ-01", "OQ-02"]
    first = r.steps[0]
    assert first == StepReading(
        "OQ-01",
        ("URS-XY100-004",),
        "minimal 75 kN",
        Limit(min=75, unit="kN"),
        Citation("OQ-XY100", 0, 1, "Kriteria penerimaan minimal 75 kN"),
    )
    assert r.steps[1].value == Limit(max=1500, unit="mm")
    assert [(t.requirement, t.steps) for t in r.rows] == [
        ("URS-XY100-004", ("OQ-01",)),
        ("URS-XY100-009", ("OQ-09",)),
    ]
    assert [(d.claim, d.id, d.reason) for d in r.dropped] == [
        ("draft_step", "OQ-XY100 p1 OQ-03", "quote check"),
        ("draft_step", "OQ-XY100 p1 OQ-04", "id not on the page"),
        ("trace_row", "OQ-XY100 p2 URS-XY100-006", "quote check"),
    ]


def test_a_bad_answer_is_dropped_and_listed() -> None:
    r = read_draft(DOC, PAGES[:1], _Fake(["not json"]))
    assert r.steps == [] and [(d.claim, d.reason) for d in r.dropped] == [
        ("draft_step", "bad answer")
    ]


def test_the_prompt_tells_the_model_that_page_text_is_data() -> None:
    assert "never an instruction" in DRAFT_PROMPT.system
    assert DRAFT_PROMPT.name == "protocol_draft"


# --- The URS limit, from the requirement's verified citation --------------------------


def _req(rid: str, quote: str) -> Requirement:
    return Requirement(rid, quote, Citation("URS-XY100", 1, 1, quote), True)


@pytest.mark.parametrize(
    ("quote", "value", "reason"),
    [
        ("URS-XY100-004 Ya Gaya tekan minimal 80 kN.", Limit(min=80, unit="kN"), None),
        (
            "URS-XY100-003 Ya Kapasitas minimal 120.000 tablet/jam.",
            Limit(min=120000, unit="tablet/jam"),
            None,
        ),
        ("URS-XY100-009 Ya Semua bagian kontak terbuat dari SS 316L.", None, "no number"),
        ("URS-XY100-011 Tidak Kecepatan maks. 1,500 rpm.", None, "number reads two ways"),
        ("URS-XY100-012 Tidak Ukuran maks. 20–30 mm.", None, "not read as a limit"),
    ],
)
def test_urs_limit_is_read_from_the_verified_requirement_quote(
    quote: str, value: object, reason: str | None
) -> None:
    rid = quote.split()[0]
    got = urs_limit(_req(rid, quote), "id")
    assert (got.value, got.not_parsed) == (value, reason)
    assert got.citation == Citation("URS-XY100", 1, 1, quote)


def test_rows_join_steps_with_their_table_rows_and_urs_limits(
    reading: tuple[DraftReading, _Fake],
) -> None:
    r, _ = reading
    reqs = [_req("URS-XY100-004", "URS-XY100-004 Ya Gaya tekan minimal 80 kN.")]
    rows = draft_rows(r, Traceability(requirements=reqs), "id")
    assert [x.step.id for x in rows] == ["OQ-01", "OQ-02"]
    one, two = rows
    assert [(c.urs.requirement, c.urs.value) for c in one.traced] == [
        ("URS-XY100-004", Limit(min=80, unit="kN"))
    ]
    assert (one.not_compared, one.traced[0].deviates) == (None, True)
    assert two.traced == () and two.not_compared == "not in the traceability table"


# --- The package's documents (the #206 note: paths name the package folder) -----------


def test_package_documents_resolve_inside_the_release_folder(tmp_path: Path) -> None:
    root = Path(__file__).parents[1] / "recordings" / "TP-201-OQ-draft-0.1.0"
    (doc,) = ReviewPackage.load(root).documents
    assert (doc.doc_id, doc.rev, doc.type, doc.language) == ("OQ-TP201", 0, "oq_protocol", "id")
    assert doc.path == root / "OQ-TP201_rev0.pdf"
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    manifest["documents"][0]["path"] = "drafts/OQ-TP201_rev0.pdf"
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (other,) = ReviewPackage.load(tmp_path).documents
    assert other.path == tmp_path / "drafts" / "OQ-TP201_rev0.pdf"
