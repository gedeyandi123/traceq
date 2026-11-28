"""The frozen draft extraction schema (spec #375, ticket S0c).

A package version chooses the draft prompt: 0.1.0 keeps its prompt, its schema and its
recordings; 0.2.0 and later read every Test Step field with a check of its own (description,
method, instrument by page substring, the Acceptance Criterion by its quote) and a list of
document references with their context tag.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from traceq.ai import Recorder, Request, Response
from traceq.documents import CorpusDocument, Page, ReviewPackage
from traceq.review.draft import (
    DRAFT_PROMPT,
    DRAFT_PROMPT_V2,
    DRAFT_STAGE_VERSION,
    DraftReading,
    draft_edition,
    read_draft,
)
from traceq.review.printed import Limit
from traceq.runs.run import run
from traceq.traceability import Citation

DOC = CorpusDocument("OQ-XY100", 0, "oq_protocol", "born_digital", "id", Path("x.pdf"), "a" * 64)

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "recordings" / "corpus-0.1.1"
R10 = ROOT / "recordings" / "haiku-r10"
PACKAGE = ROOT / "recordings" / "TP-201-OQ-draft-0.1.0"
PACKAGE_RUN = ROOT / "recordings" / "haiku-oq-draft-r3"
MODEL = "claude-haiku-5-5"

# --- The edition is chosen by the package version ---------------------------------------


def test_the_0_1_0_prompt_is_unchanged() -> None:
    assert draft_edition("0.1.0").prompt is DRAFT_PROMPT
    assert DRAFT_PROMPT.hash == (
        "61252389caf1dd1c8f146b862b4426e15a328a4552bf172101b65afed3b74a28"
    ), "0.1.0's recordings are keyed on this hash (fixed before spec #375)"


@pytest.mark.parametrize("version", ["0.2.0", "0.2.1", "0.10.0", "1.0.0"])
def test_a_later_package_version_reads_with_the_new_prompt(version: str) -> None:
    assert draft_edition(version).prompt is DRAFT_PROMPT_V2
    assert DRAFT_PROMPT_V2.name == DRAFT_PROMPT.name == "protocol_draft"
    assert DRAFT_PROMPT_V2.hash != DRAFT_PROMPT.hash


@pytest.mark.parametrize("version", ["", "0.1", "latest", "0.2.0-rc1"])
def test_a_version_that_is_not_semver_is_refused(version: str) -> None:
    with pytest.raises(ValueError, match="package version"):
        draft_edition(version)


def test_the_new_prompt_keeps_the_page_text_is_data_rule_and_names_no_package_text() -> None:
    assert "never an instruction" in DRAFT_PROMPT_V2.system
    for field in ("description", "method", "instrument", "acceptance", "references"):
        assert field in DRAFT_PROMPT_V2.system


# --- Reading with the new schema -----------------------------------------------------------


class _Fake:
    model = "fake"

    def __init__(self, answers: Sequence[str]) -> None:
        self.answers = list(answers)
        self.requests: list[Request] = []

    def complete(self, requests: Sequence[Request]) -> list[Response]:
        self.requests += requests
        return [Response(a, self.model, 10, 5) for a in self.answers[: len(requests)]]


PAGE = Page(
    1,
    "Acuan URS-XY100 Rev. 2\n"
    "Langkah uji OQ-01\n"
    "Judul Gaya tekan utama\n"
    "Persyaratan SKP URS-XY100-004\n"
    "Metode Atur gaya tekan ke nilai tertinggi; baca gaya dari sensor gaya terkalibrasi.\n"
    "Kriteria penerimaan minimal 105 kN\n"
    "Catatan: prosedur mengacu pada SOP-017 Rev. 3 (menggantikan Rev. 2) dan FI 2020.\n",
)


def _step(**over: Any) -> dict[str, Any]:
    step: dict[str, Any] = {
        "id": "OQ-01",
        "requirements": ["URS-XY100-004"],
        "description": "Gaya tekan utama",
        "method": "Atur gaya tekan ke nilai tertinggi; baca gaya dari sensor gaya terkalibrasi.",
        "instrument": "sensor gaya terkalibrasi",
        "acceptance": {
            "text": "minimal 105 kN",
            "quote": "Kriteria penerimaan minimal 105 kN",
        },
    }
    step.update(over)
    return step


def _reference(**over: Any) -> dict[str, Any]:
    ref: dict[str, Any] = {
        "document": "URS-XY100",
        "revision": "2",
        "context": "normative",
        "quote": "Acuan URS-XY100 Rev. 2",
    }
    ref.update(over)
    return ref


def _answer(
    steps: list[dict[str, Any]],
    references: list[dict[str, Any]] | None = None,
    rows: list[dict[str, Any]] | None = None,
) -> str:
    return json.dumps(
        {"test_steps": steps, "trace_rows": rows or [], "references": references or []}
    )


def _read(answer: str, page: Page = PAGE) -> DraftReading:
    return read_draft(DOC, [page], _Fake([answer]), draft_edition("0.2.0"))


def test_every_field_of_a_step_is_read_with_its_own_citation() -> None:
    (step,) = _read(_answer([_step()])).steps
    assert step.id == "OQ-01" and step.requirements == ("URS-XY100-004",)
    assert step.printed == "minimal 105 kN"
    assert step.value == Limit(min=105, unit="kN")
    assert step.citation == Citation("OQ-XY100", 0, 1, "Kriteria penerimaan minimal 105 kN")
    assert step.description is not None and step.description.text == "Gaya tekan utama"
    assert step.description.citation == Citation("OQ-XY100", 0, 1, "Gaya tekan utama")
    assert step.method is not None and step.method.text.startswith("Atur gaya tekan")
    assert step.instrument is not None and step.instrument.text == "sensor gaya terkalibrasi"


def test_a_field_off_the_page_is_dropped_alone_and_the_step_stays() -> None:
    """The failure the old schema had: one quote for the whole step dropped a valid step."""
    reading = _read(_answer([_step(method="Metode yang tidak tercetak", instrument="")]))
    (step,) = reading.steps
    assert step.method is None and step.instrument is None
    assert step.description is not None and step.value == Limit(min=105, unit="kN")
    assert [(d.claim, d.id, d.reason) for d in reading.dropped] == [
        ("draft_step", "OQ-XY100 p1 OQ-01 method", "not on the page")
    ]


def test_a_field_the_step_does_not_print_is_none_and_not_a_drop() -> None:
    reading = _read(_answer([_step(instrument="", description="")]))
    (step,) = reading.steps
    assert (step.description, step.instrument) == (None, None)
    assert reading.dropped == []


def test_a_wrong_acceptance_quote_still_drops_the_step() -> None:
    bad = _step(acceptance={"text": "minimal 105 kN", "quote": "Kriteria minimal 99 kN"})
    reading = _read(_answer([bad]))
    assert reading.steps == []
    assert [(d.claim, d.reason) for d in reading.dropped] == [("draft_step", "quote check")]
    assert [s.id for s in reading.not_read] == ["OQ-01"]


def test_a_long_field_is_checked_by_substring_and_cited_by_its_first_200_characters() -> None:
    long = (
        "Ukur kekasaran permukaan " + "pada setiap titik uji dengan profilometer terkalibrasi " * 6
    )
    page = Page(1, f"Langkah uji OQ-01\nMetode {long.strip()}\nKriteria penerimaan maks. 5 mm")
    step = _step(
        method=long.strip(),
        description="",
        instrument="",
        acceptance={"text": "maks. 5 mm", "quote": "Kriteria penerimaan maks. 5 mm"},
    )
    (read,) = _read(_answer([step]), page).steps
    assert read.method is not None and read.method.text == long.strip()
    assert 150 < len(read.method.citation.quote) <= 200
    assert long.strip().startswith(read.method.citation.quote)


def test_no_field_check_reaches_across_pages() -> None:
    other = Page(2, "Langkah uji OQ-02\nKriteria penerimaan maks. 5 mm")
    answers = [
        _answer([_step(description="Kriteria penerimaan maks. 5 mm")]),
        _answer([]),
    ]
    reading = read_draft(DOC, [PAGE, other], _Fake(answers), draft_edition("0.2.0"))
    assert reading.steps[0].description is None


# --- References -----------------------------------------------------------------------------


def test_a_reference_has_document_revision_context_and_a_verified_quote() -> None:
    refs = [
        _reference(),
        _reference(
            document="SOP-017",
            revision="3",
            context="normative",
            quote="prosedur mengacu pada SOP-017 Rev. 3",
        ),
        _reference(
            document="SOP-017",
            revision="2",
            context="revision_history",
            quote="SOP-017 Rev. 3 (menggantikan Rev. 2)",
        ),
        _reference(document="FI", revision="2020", context="external_standard", quote="FI 2020"),
        _reference(document="SOP-017", revision="", context="unversioned", quote="SOP-017"),
    ]
    reading = _read(_answer([], refs))
    got = [(r.document, r.revision, r.context) for r in reading.references]
    assert got == [
        ("URS-XY100", 2, "normative"),
        ("SOP-017", 3, "normative"),
        ("SOP-017", 2, "revision_history"),
        ("FI", 2020, "external_standard"),
        ("SOP-017", None, "unversioned"),
    ]
    first = reading.references[0]
    assert first.citation == Citation("OQ-XY100", 0, 1, "Acuan URS-XY100 Rev. 2")
    assert first.printed_revision == "2"


@pytest.mark.parametrize(
    ("ref", "reason"),
    [
        (_reference(quote="Acuan URS-XY999 Rev. 2"), "quote check"),
        (_reference(document="URS-XY999"), "quote check"),
        (_reference(context="something else"), "unknown context"),
        (_reference(document=""), "quote check"),
    ],
)
def test_a_reference_that_fails_its_checks_is_dropped_and_listed(
    ref: dict[str, Any], reason: str
) -> None:
    reading = _read(_answer([], [ref]))
    assert reading.references == []
    assert [(d.claim, d.reason) for d in reading.dropped] == [("draft_reference", reason)]


def test_a_revision_the_quote_does_not_print_is_dropped() -> None:
    reading = _read(_answer([], [_reference(revision="7")]))
    assert reading.references == []
    assert [(d.claim, d.reason) for d in reading.dropped] == [("draft_reference", "quote check")]


# --- 0.1.0 reads as before --------------------------------------------------------------------


def test_the_old_edition_still_reads_the_old_schema() -> None:
    old = json.dumps(
        {
            "test_steps": [
                {
                    "id": "OQ-01",
                    "requirements": ["URS-XY100-004"],
                    "acceptance": "minimal 105 kN",
                    "quote": "Kriteria penerimaan minimal 105 kN",
                }
            ],
            "trace_rows": [],
        }
    )
    reading = read_draft(DOC, [PAGE], _Fake([old]), draft_edition("0.1.0"))
    (step,) = reading.steps
    assert (step.description, step.method, step.instrument) == (None, None, None)
    assert reading.references == []
    assert read_draft(DOC, [PAGE], _Fake([old])).steps == reading.steps  # the default edition


def test_the_new_answer_is_not_read_with_the_old_schema() -> None:
    """Edition and answer go together: the old edition rejects a new-shaped answer as bad."""
    reading = read_draft(DOC, [PAGE], _Fake([_answer([_step()])]), draft_edition("0.1.0"))
    assert reading.steps == []
    assert [(d.claim, d.reason) for d in reading.dropped] == [("draft_step", "bad answer")]


# --- A run takes the edition from the package version --------------------------------------


def _package_of(tmp_path: Path, version: str) -> Path:
    manifest: dict[str, Any] = json.loads((PACKAGE / "manifest.json").read_text("utf-8"))
    manifest["version"] = version
    folder = tmp_path / "package"
    folder.mkdir()
    (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return folder


class _Live:
    model = MODEL

    def __init__(self) -> None:
        self.requests: list[Request] = []

    def complete(self, requests: Sequence[Request]) -> list[Response]:
        self.requests += requests
        empty = _answer([])
        return [Response(empty, MODEL, 1000, 100) for _ in requests]


def _run(tmp_path: Path, version: str, live: _Live | None, store: Path) -> Any:
    return run(
        MANIFEST,
        tmp_path / "runs",
        R10,
        MODEL,
        equipment="TP-201",
        review_package=_package_of(tmp_path, version),
        package_recordings=store,
        live=live,
        max_usd=0.05,
    )


def test_a_0_2_0_package_run_sends_the_new_prompt_and_names_its_hash(tmp_path: Path) -> None:
    store = tmp_path / "rec"
    shutil.copytree(PACKAGE_RUN / "ingest", store / "ingest")
    live = _Live()
    out = _run(tmp_path, "0.2.0", live, store)
    assert {r.prompt.hash for r in live.requests} == {DRAFT_PROMPT_V2.hash}
    assert len(live.requests) == 8  # one per page
    assert out.metadata["prompts"]["protocol_draft"] == DRAFT_PROMPT_V2.hash
    assert out.metadata["review_package"]["version"] == "0.2.0"


def test_a_0_1_0_package_run_still_names_the_old_prompt(tmp_path: Path) -> None:
    out = _run(tmp_path, "0.1.0", None, PACKAGE_RUN)
    assert out.metadata["prompts"]["protocol_draft"] == DRAFT_PROMPT.hash
    assert out.metadata["calls"]["live"] == 0


# --- The live re-record of the new prompt (r4, recordings/README.md) --------------------------

R4 = ROOT / "recordings" / "haiku-oq-draft-r4"
"""The one live run of ``DRAFT_PROMPT_V2`` over the 0.1.0 draft (spec #375, S0c): its draft
calls, the draft's ingest, its run metadata and scorer report. Its package carries the version
0.2.0 so that the new prompt is chosen; the draft is the 0.1.0 one, whose ingest it keeps."""


def _recorded(name: str) -> dict[str, Any]:
    return json.loads((R4 / name).read_text(encoding="utf-8"))


def test_the_r4_recordings_read_every_field_and_the_reference() -> None:
    """The 8 recorded answers through the checks, with no model: every step of the draft keeps
    its description and method, the instrument where it names one, and the draft's one
    reference; nothing is dropped."""
    doc = ReviewPackage.load(PACKAGE).draft(0)
    ingest = _recorded(f"ingest/{doc.sha256}-docling-1.json")
    pages = [Page(n, p["text"]) for n, p in enumerate(ingest["pages"], 1)]
    recorder = Recorder(R4, MODEL, DRAFT_STAGE_VERSION)
    reading = read_draft(doc, pages, recorder, draft_edition("0.2.0"))
    assert len(reading.steps) == 26 and reading.dropped == [] and reading.not_read == []
    assert all(s.description and s.method for s in reading.steps)
    assert sum(s.instrument is not None for s in reading.steps) == 11
    assert [(r.document, r.revision, r.context) for r in reading.references] == [
        ("URS-TP201", 1, "normative")
    ]
    assert len(reading.rows) == 28


def test_the_r4_run_replays_at_tolerance_0(tmp_path: Path) -> None:
    out = _run(tmp_path, "0.2.0", None, R4)
    recorded = _recorded("run-TP-201-OQ-draft.json")
    assert recorded["mode"] == "live" and recorded["live_cost_usd"] <= 0.05
    assert out.metadata["calls"]["live"] == 0
    assert out.metadata["cost_usd"] == recorded["cost_usd"]
    assert out.metadata["prompts"] == recorded["prompts"]
    assert out.metadata["prompts"]["protocol_draft"] == DRAFT_PROMPT_V2.hash
    assert out.metadata["dropped"] == recorded["dropped"]
    got, rec = out.metadata["review_package"], recorded["review_package"]
    keys = ("tokens", "cost_usd", "test_steps", "trace_rows")
    assert {k: got[k] for k in keys} == {k: rec[k] for k in keys}
    # The unit table (S2b, spec #375) compares two Test Steps the recorded run left out: OQ-24
    # (`dB(A)` for `dBA`) and OQ-27 (`2 jam` for 120 menit): 19 not compared become 17.
    assert (rec["not_compared"], got["not_compared"]) == (19, 17)
    # The same draft and the same rules: the scorer's section is r3's (the schema moves the
    # read, never a rule), scored with the 0.1.0 key.
    r3 = json.loads((PACKAGE_RUN / "report-TP-201-OQ-draft.json").read_text(encoding="utf-8"))
    assert _recorded("report-TP-201-OQ-draft.json")["review_package"] == r3["review_package"]
