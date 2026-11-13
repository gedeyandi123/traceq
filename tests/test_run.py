"""``traceq run`` end to end (spec #29, primary seam): a released corpus in, a run folder out,
the submission scored by the real scorer. The LLM is a scripted fake; nothing is sent."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import pytest

from traceq.ai import BudgetExceeded, PriceTable, Request, Response
from traceq.ai.cost import Price
from traceq.documents import OcrUnavailable, pdf
from traceq.runs import cli
from traceq.runs.run import RunOutput, run
from traceq_dataset import render
from traceq_dataset.answer_key import load_key
from traceq_dataset.corpus import build_corpus
from traceq_dataset.world import load
from traceq_eval.citations import PageTexts
from traceq_eval.ocr import score_ocr
from traceq_eval.score import score
from traceq_eval.submission import Submission

ROOT = Path(__file__).parents[1]
TP201 = ROOT / "world" / "tp201.yaml"
KEY = ROOT / "answer_key" / "TP-201"
MODEL = "scripted"
PRICES = PriceTable(batch_discount=0.5, models={MODEL: Price(1.0, 2.0)})

FABRICATED_QUOTE = "Gaya pra-kompresi yang dapat dicapai minimal 50 kN."
SCRIPT: dict[str, dict[str, Any]] = {
    "URS-TP201-001": {"kind": "range", "min": 36, "unit": "stations"},
    "URS-TP201-002": {"kind": "range", "min": 20, "max": 70, "unit": "rpm"},
    "URS-TP201-004": {"kind": "range", "min": 100, "unit": "kN"},
    # Not on the page: the citation check must drop it.
    "URS-TP201-005": {"kind": "range", "min": 50, "unit": "kN", "quote": FABRICATED_QUOTE},
    # Quote on the page, but it says 25 mm: the value is not in the quote.
    "URS-TP201-006": {"kind": "range", "max": 30, "unit": "mm"},
    "URS-TP201-008": {"kind": "one_of", "allowed": ["EU D"]},
    "URS-TP201-012": {"kind": "one_of", "allowed": ["EPDM", "silicone"]},
    "URS-TP201-014": {"kind": "present"},
    "URS-TP201-026": {"kind": "number", "number": 380, "unit": "V"},
}
INVENTED = {"id": "URS-TP201-999", "text": "Mesin dapat terbang.", "quote": "Mesin dapat terbang."}

BLANK_VALUE = {
    "min": None,
    "max": None,
    "number": None,
    "unit": None,
    "text": None,
    "present": None,
}
# Test steps the scripted model reads: step -> (observed as printed, value).
STEPS: dict[str, tuple[str, dict[str, Any]]] = {
    "FAT-M-01": ("36 stations", {"kind": "number", "number": 36, "unit": "stations"}),
    "FAT-M-02": ("20–60 rpm", {"kind": "range", "min": 20, "max": 60, "unit": "rpm"}),
    "FAT-M-03": ("96 kN", {"kind": "number", "number": 96, "unit": "kN"}),
    "FAT-M-12": ("Present and functional", {"kind": "present", "present": True}),
    "FAT-C-01": ("Present and functional", {"kind": "present", "present": True}),
}
FABRICATED_STEP = {"step": "FAT-M-99", "quote": "FAT-M-99 Fly the press. Flies Pass"}
# Datasheet rows: label -> (value as printed, value).
ROWS: dict[str, tuple[str, dict[str, Any]]] = {
    "Turret speed": ("20–70 rpm", {"kind": "range", "min": 20, "max": 70, "unit": "rpm"}),
    "Tooling standard": ("EU B", {"kind": "text", "text": "EU B"}),
}
# Requirement -> (step ids, row labels, site_only, transport_sensitive).
LINKS: dict[str, tuple[list[str], list[str], bool, bool]] = {
    "URS-TP201-001": (["FAT-TP201-M/FAT-M-01"], [], False, False),
    "URS-TP201-002": (["FAT-TP201-M/FAT-M-02"], ["Turret speed"], False, False),
    "URS-TP201-004": (["FAT-TP201-M/FAT-M-03", "FAT-TP201-M/FAT-M-99"], [], False, False),
    "URS-TP201-008": ([], ["Tooling standard"], False, False),
    # A lure (hallucination probe P1): a certificate check says nothing about the gasket.
    "URS-TP201-012": (["FAT-TP201-M/FAT-M-12"], [], False, False),
    "URS-TP201-014": (["FAT-TP201-C/FAT-C-01"], [], False, False),
    "URS-TP201-026": ([], [], True, False),
}
EXPECTED_COVERAGE = {
    # No Vendor Assessment is in the corpus: condition 1 never holds.
    "URS-TP201-001": ("partial", "FAT-M-01: condition 1: no Vendor Assessment"),
    "URS-TP201-002": ("partial", "FAT-M-02: condition 1: no Vendor Assessment"),
    "URS-TP201-004": ("partial", "FAT-M-03: result does not meet the URS"),
    "URS-TP201-008": ("conflict", "DS-TP201 does not meet the URS"),
    "URS-TP201-012": ("gap", "no FAT/SAT step addresses it"),
    "URS-TP201-014": ("partial", "FAT-C-01: condition 1: no Vendor Assessment"),
    "URS-TP201-026": ("site_only", "cannot be tested by the vendor"),
    "URS-TP201-003": ("gap", "no FAT/SAT step addresses it"),
}


def _page(r: Request) -> str:
    return r.user.split("<page>\n", 1)[1].rsplit("\n</page>", 1)[0]


def _facts(r: Request) -> dict[str, Any]:
    page = _page(r)
    lines = page.splitlines()

    def line(pattern: str) -> re.Match[str] | None:
        return next((m for x in lines if (m := re.match(pattern, x))), None)

    approved = line(r"^Approved by .*Customer \(site\).* (\d{2}-\w{3}-\d{4})$")
    executed = line(r"^Executed by .* (\d{2}-\w{3}-\d{4})$")
    steps = [
        {
            "step": sid,
            "test": "",
            "acceptance": "",
            "observed": observed,
            "result": "pass",
            "value": BLANK_VALUE | value,
            "quote": m[0],
        }
        for sid, (observed, value) in STEPS.items()
        if (m := line(rf"^{sid} .*$"))
    ]
    if "FAT-M-01" in page:
        steps.append(
            {"test": "", "acceptance": "", "observed": "Flies", "result": "pass"}
            | {"value": BLANK_VALUE | {"kind": "present", "present": True}}
            | FABRICATED_STEP
        )
    rows = [
        {"name": name, "printed": printed, "value": BLANK_VALUE | value, "quote": m[0]}
        for name, (printed, value) in ROWS.items()
        if (m := line(rf"^{name} .*$"))
    ]
    return {
        "site_approved_on": approved and {"date": approved[1], "quote": approved[0]},
        "executed_on": executed and {"date": executed[1], "quote": executed[0]},
        "steps": steps,
        "rows": rows,
    }


def _link(r: Request) -> dict[str, Any]:
    asked = json.loads(r.user)
    steps, rows, site_only, transport = LINKS.get(asked["requirement"]["id"], ([], [], False, True))
    by_name = {row["name"]: row["id"] for row in asked["rows"]}
    return {
        "steps": steps,
        "rows": [by_name[name] for name in rows],
        "site_only": site_only,
        "transport_sensitive": transport,
    }


class ScriptedLLM:
    """Segments by the printed requirement numbers, extracts from ``SCRIPT``, reads the
    vendor facts in ``STEPS`` and ``ROWS`` and links by ``LINKS``."""

    def __init__(self) -> None:
        self.sent: list[Request] = []

    @property
    def model(self) -> str:
        return MODEL

    def complete(self, requests: Sequence[Request]) -> list[Response]:
        self.sent += requests
        return [Response(self._answer(r), MODEL, len(r.user) // 4, 40) for r in requests]

    def _answer(self, r: Request) -> str:
        if r.prompt.name == "facts":
            return json.dumps(_facts(r))
        if r.prompt.name == "link":
            return json.dumps(_link(r))
        if r.prompt.name == "segment":
            page = _page(r)
            found = [
                {"id": m[1], "text": m[2], "quote": m[2]}
                for m in re.finditer(r"^(URS-\w+-\d{3}) (?:Ya|Tidak) (.+?)\s*$", page, re.M)
            ]
            if "page 1." in r.user:
                found.append(INVENTED)
            return json.dumps({"requirements": found})
        head = json.loads(r.user.split("\n\n", 1)[0])
        blank = {"kind": "none", "min": None, "max": None, "number": None, "unit": None}
        answer = {**blank, "allowed": [], "text": None, "quote": head["requirement"]}
        return json.dumps(answer | SCRIPT.get(head["id"], {}))


@pytest.fixture(scope="module")
def corpus_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("dist")
    assert render.main([str(TP201), "--out", str(out)]) == 0
    return next(out.glob("t0-*"))


Seed = Callable[[Path, Path], None]


@pytest.fixture(scope="module")
def seeded(corpus_dir: Path, seed_scans: Seed) -> Callable[[Path], Path]:
    """A recordings directory whose ingest cache holds the recorded OCR output of the
    scans, so no test here needs the OCR model."""

    def seed(recordings: Path) -> Path:
        seed_scans(corpus_dir, recordings / "ingest")
        return recordings

    return seed


@pytest.fixture(scope="module")
def recorded(
    corpus_dir: Path, seeded: Callable[[Path], Path], tmp_path_factory: pytest.TempPathFactory
) -> RunOutput:
    tmp = tmp_path_factory.mktemp("live")
    seeded(tmp / "recordings")
    return run(
        corpus_dir, tmp / "runs", tmp / "recordings", MODEL, live=ScriptedLLM(), prices=PRICES
    )


def _req(sub: dict[str, Any], rid: str) -> dict[str, Any]:
    return next(r for r in sub["requirements"] if r["id"] == rid)


def test_submission_validates_and_passes_the_scorer_gates(recorded: RunOutput) -> None:
    text = (recorded.folder / "submission.json").read_text(encoding="utf-8")
    sub = Submission.model_validate_json(text)
    report = score(sub, load_key(KEY), PageTexts(build_corpus(load(TP201))))

    assert report["gates"]["passed"], report["gates"]
    items = {i["id"]: i for i in report["requirements"]["items"]}
    assert [rid for rid in SCRIPT if items[rid]["value_ok"]] == [
        "URS-TP201-001",
        "URS-TP201-002",
        "URS-TP201-004",
        "URS-TP201-008",
        "URS-TP201-012",
        "URS-TP201-014",
    ]
    assert report["requirements"]["metrics"]["source_citation_rate"] == 1.0
    assert report["requirements"]["metrics"]["unknown_requirements"] == []
    assert report["requirements"]["metrics"]["superseded_values"] == 0


def test_coverage_is_decided_by_the_decision_table(recorded: RunOutput) -> None:
    sub = Submission.model_validate_json(
        (recorded.folder / "submission.json").read_text(encoding="utf-8")
    )
    report = score(sub, load_key(KEY), PageTexts(build_corpus(load(TP201))))
    matrix = json.loads((recorded.folder / "matrix.json").read_text(encoding="utf-8"))
    rows = {r["id"]: r for r in matrix["requirements"]}

    assert all(r.coverage is not None for r in sub.requirements)
    assert all(r["coverage"] and r["reason"] for r in rows.values())
    assert {rid: (rows[rid]["coverage"], rows[rid]["reason"]) for rid in EXPECTED_COVERAGE} == (
        EXPECTED_COVERAGE
    )
    items = {i["id"]: i for i in report["requirements"]["items"]}
    assert [rid for rid in EXPECTED_COVERAGE if items[rid]["coverage_ok"]] == [
        "URS-TP201-002",
        "URS-TP201-004",
        "URS-TP201-008",
        "URS-TP201-012",
        "URS-TP201-014",
        "URS-TP201-026",
    ]
    assert report["requirements"]["metrics"]["evidence_precision"] == 1.0
    assert report["citations"]["by_status"]["verified"] == report["citations"]["total"]
    probes = {p["requirement"]: p for p in report["probes"]["items"] if p["absent"] == "evidence"}
    assert probes["URS-TP201-012"]["status"] == "not_found"


def test_each_requirement_cites_its_evidence(recorded: RunOutput) -> None:
    sub = json.loads((recorded.folder / "submission.json").read_text(encoding="utf-8"))
    matrix = json.loads((recorded.folder / "matrix.json").read_text(encoding="utf-8"))
    rows = {r["id"]: r for r in matrix["requirements"]}

    speed = rows["URS-TP201-002"]
    (step,) = speed["evidence"]
    assert (step["doc"], step["step"], step["failure"]) == (
        "FAT-TP201-M",
        "FAT-M-02",
        "condition 1: no Vendor Assessment",
    )
    assert step["citation"]["page"] == 1 and "FAT-M-02" in step["citation"]["quote"]
    assert [d["printed"] for d in speed["design"]] == ["20–70 rpm"]
    assert _req(sub, "URS-TP201-002")["evidence"] == [
        {"doc": "FAT-TP201-M", "rev": 0, "step": "FAT-M-02"}
    ]
    quotes = [c["quote"] for c in _req(sub, "URS-TP201-002")["citations"]]
    assert len(quotes) == 3 and step["citation"]["quote"] in quotes
    # The design row behind the conflict is cited.
    tooling = _req(sub, "URS-TP201-008")
    assert tooling["coverage"] == "conflict"
    assert any("EU B" in c["quote"] for c in tooling["citations"])
    # Scans are read through OCR: every vendor record is read.
    assert matrix["not_read"] == []


def test_an_unverifiable_claim_never_reaches_the_submission(recorded: RunOutput) -> None:
    text = (recorded.folder / "submission.json").read_text(encoding="utf-8")
    sub = json.loads(text)
    assert FABRICATED_QUOTE not in text
    assert INVENTED["id"] not in text
    for rid in ("URS-TP201-005", "URS-TP201-006"):
        r = _req(sub, rid)
        assert "value" not in r, rid
        assert [c.get("value") for c in r["citations"]] == [None], rid
    dropped = {(d["claim"], d["id"]) for d in recorded.metadata["dropped"]}
    assert dropped == {
        ("requirement", "URS-TP201-999"),
        ("value", "URS-TP201-005"),
        ("value", "URS-TP201-006"),
        ("step", "FAT-TP201-M/FAT-M-99"),
        ("link", "URS-TP201-004 FAT-TP201-M/FAT-M-99"),
    }
    assert FABRICATED_STEP["quote"] not in text


def test_run_metadata_records_model_prompts_tokens_and_cost(recorded: RunOutput) -> None:
    meta = json.loads((recorded.folder / "run.json").read_text(encoding="utf-8"))
    assert meta["model"] == MODEL
    assert meta["mode"] == "live"
    assert set(meta["prompts"]) == {"segment", "extract", "facts", "link"}
    assert all(re.fullmatch(r"[0-9a-f]{64}", h) for h in meta["prompts"].values())
    # One segmentation call per URS page, one extraction and one link per requirement, one
    # fact call per page of FAT-TP201-M (2), FAT-TP201-C (1), SAT-TP201 (2, a scan),
    # DS-TP201 (1) and MTC-TP201-01 (1, a scan).
    calls = 2 + 38 + 38 + 7
    assert meta["calls"] == {"total": calls, "replayed": 0, "live": calls}
    assert meta["tokens"]["output"] == 40 * calls
    expected = (meta["tokens"]["input"] * 1.0 + meta["tokens"]["output"] * 2.0) / 1e6 * 0.5
    assert meta["cost_usd"] == pytest.approx(expected, abs=1e-6)
    assert meta["live_cost_usd"] == pytest.approx(expected, abs=1e-6)
    assert [(d["doc_id"], d["rev"]) for d in meta["corpus"]["documents"]] == [
        ("URS-TP201", 1),
        ("FAT-TP201-M", 0),
        ("FAT-TP201-C", 0),
        ("SAT-TP201", 0),
        ("DS-TP201", 0),
        ("MTC-TP201-01", 0),
    ]


def test_run_metadata_logs_ingest_time_and_peak_ram(recorded: RunOutput) -> None:
    meta = json.loads((recorded.folder / "run.json").read_text(encoding="utf-8"))
    ingest = {(d["doc_id"], d["rev"]): d for d in meta["ingest"]}
    sat = ingest[("SAT-TP201", 0)]
    assert sat["engine"] == "PP-OCRv6 small via RapidOCR 3.10.0"
    assert sat["pages"] == 2 and len(sat["seconds_per_page"]) == 2
    assert all(s > 0 for s in sat["seconds_per_page"])
    assert sat["peak_ram_bytes"] > 0
    assert sat["cached"]
    assert {d["format"] for d in meta["ingest"]} == {"born_digital", "scan"}
    assert all(len(d["seconds_per_page"]) == d["pages"] for d in meta["ingest"])


def test_submission_carries_the_scan_entries_for_the_ocr_scorer(recorded: RunOutput) -> None:
    sub = Submission.model_validate_json(
        (recorded.folder / "submission.json").read_text(encoding="utf-8")
    )
    report = score_ocr(sub, load_key(KEY))
    assert {e.doc for e in sub.ocr} == {
        "SAT-TP201",
        "MTC-TP201-01",
        "KAL-2025-0412",
        "KAL-2026-0057",
        "CAL-TP201-01",
    }
    assert all(e.quad is not None for e in sub.ocr)
    assert report["metrics"]["entry_recall"] == 1.0
    assert report["metrics"]["exact_match_rate"] == round(35 / 36, 4)


@pytest.mark.usefixtures("no_ocr_model")
def test_replay_reproduces_the_run_without_sending(
    recorded: RunOutput, corpus_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """As in CI: neither Docling nor the OCR model runs; ingest comes from the cache."""

    def no_docling() -> None:
        raise AssertionError("Docling ran on a replay")

    monkeypatch.setattr(pdf, "_converter", no_docling)
    recordings = recorded.folder.parents[1] / "recordings"
    argv = ["run", str(corpus_dir), "--out", str(tmp_path), "--recordings", str(recordings)]
    assert cli.main([*argv, "--model", MODEL]) == 0
    (folder,) = tmp_path.iterdir()
    replayed = json.loads((folder / "submission.json").read_text(encoding="utf-8"))
    assert (
        replayed["requirements"]
        == recorded.submission.model_dump(mode="json", exclude_none=True)["requirements"]
    )
    assert replayed["ocr"] == recorded.submission.model_dump(mode="json")["ocr"]
    meta = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    assert meta["calls"]["live"] == 0
    assert meta["tokens"] == recorded.metadata["tokens"]
    assert all(d["cached"] for d in meta["ingest"])


def test_replay_fails_on_a_missing_recording(
    corpus_dir: Path, tmp_path: Path, seeded: Callable[[Path], Path]
) -> None:
    recordings = seeded(tmp_path / "none")
    argv = ["run", str(corpus_dir), "--out", str(tmp_path / "runs")]
    assert cli.main([*argv, "--recordings", str(recordings), "--model", MODEL]) == 2
    assert not (tmp_path / "runs").exists()


@pytest.mark.usefixtures("no_ocr_model")
def test_a_scan_neither_cached_nor_readable_fails_before_any_call(
    corpus_dir: Path, tmp_path: Path
) -> None:
    llm = ScriptedLLM()
    with pytest.raises(OcrUnavailable):
        run(corpus_dir, tmp_path / "runs", tmp_path / "rec", MODEL, live=llm, prices=PRICES)
    assert llm.sent == []
    argv = ["run", str(corpus_dir), "--out", str(tmp_path / "runs"), "--model", MODEL]
    assert cli.main([*argv, "--recordings", str(tmp_path / "rec")]) == 2


def test_live_run_over_budget_refuses_before_sending(
    corpus_dir: Path, tmp_path: Path, seeded: Callable[[Path], Path]
) -> None:
    seeded(tmp_path / "rec")
    llm = ScriptedLLM()
    with pytest.raises(BudgetExceeded):
        run(
            corpus_dir,
            tmp_path / "runs",
            tmp_path / "rec",
            MODEL,
            live=llm,
            max_usd=0.0001,
            prices=PRICES,
        )
    assert llm.sent == []
    assert not list((tmp_path / "rec").glob("*.json"))  # no LLM recording; ingest is cached


def test_live_run_with_an_unpriced_model_refuses(
    corpus_dir: Path, tmp_path: Path, seeded: Callable[[Path], Path]
) -> None:
    seeded(tmp_path / "rec")
    llm = ScriptedLLM()
    with pytest.raises(BudgetExceeded, match="no price"):
        run(corpus_dir, tmp_path / "runs", tmp_path / "rec", MODEL, live=llm)
    assert llm.sent == []
