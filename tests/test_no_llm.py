"""The No-LLM Baseline (#193): a rules-only adapter behind the LLM port, so the figures of a
run without a model show what the LLM adds.

Unit examples are invented (an imaginary granulator, GR-901); the pinned figures replay the
baseline on TP-201 from the r10 ingest cache, as ``tests/test_recorded_runs.py`` does.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from traceq.ai import Prompt, Request
from traceq.app.cli import main
from traceq.protocols.prompts import PROMPTS as PROTOCOLS
from traceq.review.prompts import PROMPTS as REVIEW
from traceq.runs.no_llm import MODEL, NoLLM
from traceq.traceability.prompts import PROMPTS as TRACEABILITY
from traceq_dataset.answer_key import load_key
from traceq_dataset.corpus import build_corpus
from traceq_dataset.world import load
from traceq_eval.citations import PageTexts
from traceq_eval.score import score
from traceq_eval.submission import Submission

ROOT = Path(__file__).resolve().parents[1]
RECORDINGS = ROOT / "recordings" / "haiku-r10"
MANIFEST = ROOT / "recordings" / "corpus-0.1.1"
PROMPTS = {p.name: p for p in (*TRACEABILITY, *REVIEW, *PROTOCOLS)}


def _valid(value: Any, schema: dict[str, Any], where: str = "$") -> list[str]:
    """The ways ``value`` breaks the subset of JSON Schema the prompts use."""
    types = schema.get("type", [])
    types = [types] if isinstance(types, str) else types
    kinds = {
        "object": dict,
        "array": list,
        "string": str,
        "boolean": bool,
        "null": type(None),
    }
    ok = any(
        (t == "integer" and isinstance(value, int) and not isinstance(value, bool))
        or (t == "number" and isinstance(value, int | float) and not isinstance(value, bool))
        or (t in kinds and isinstance(value, kinds[t]))
        for t in types
    )
    if not ok:
        return [f"{where}: {value!r} is not {types}"]
    errors: list[str] = []
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{where}: {value!r} not in {schema['enum']}")
    if isinstance(value, dict):
        props: dict[str, Any] = schema.get("properties", {})
        errors += [f"{where}: missing {k}" for k in schema.get("required", []) if k not in value]
        if schema.get("additionalProperties") is False:
            errors += [f"{where}: extra {k}" for k in value if k not in props]
        for k, v in value.items():
            if k in props:
                errors += _valid(v, props[k], f"{where}.{k}")
    if isinstance(value, list) and "items" in schema:
        for i, v in enumerate(value):
            errors += _valid(v, schema["items"], f"{where}[{i}]")
    return errors


def _page(text: str, doc: str = "X-1", page: int = 1) -> str:
    return f"Document {doc}, revision 0, page {page}.\n\n<page>\n{text}\n</page>"


def _document(*pages: str, doc: str = "X-1") -> str:
    body = "\n\n".join(f'<page n="{n}">\n{t}\n</page>' for n, t in enumerate(pages, 1))
    return f"Document {doc}, revision 0, {len(pages)} pages.\n\n{body}"


URS = (
    "1. Performance\n"
    "No. Critical Requirement\n"
    "URS-GR901-001 Yes The bowl volume is 20–80 L.\n"
    "URS-GR901-002 No Impeller speed at least 150 rpm.\n"
    "URS-GR901-003 Yes Product-contact parts are made of SS 316L or Hastelloy.\n"
    "URS-GR901-004 No An operating manual is available.\n"
)
VENDOR = (
    "Approved by Ana Lima Customer (site) Signed electronically 03-Mar-2026\n"
    "Step Test Acceptance criterion Result Pass/Fail\n"
    "FAT-01 Fill the bowl and read the volume. 20–80 L 20–80 L Pass\n"
    "FAT-02 Run the impeller at top speed. ≥ 150 rpm 162 rpm Pass\n"
    "Executed by Tom Berg Vendor GmbH Signed electronically 05-Mar-2026\n"
)
LINK = json.dumps(
    {
        "requirement": {
            "id": "URS-GR901-002",
            "text": "Impeller speed at least 150 rpm.",
            "value": {"type": "range", "min": 150.0, "max": None, "unit": "rpm"},
        },
        "steps": [
            {"id": "F/FAT-01", "test": "Fill the bowl.", "acceptance": "20–80 L", "observed": "x"},
            {
                "id": "F/FAT-02",
                "test": "Run the impeller at top speed.",
                "acceptance": "≥ 150 rpm",
                "observed": "162 rpm",
            },
        ],
        "rows": [{"id": "DS#p1.1", "name": "Impeller speed", "value": "50–200 rpm"}],
        "areas": ["Mechanical"],
    }
)
DRAFT_WITH_VALUE = json.dumps(
    {
        "requirement": {
            "id": "URS-GR901-002",
            "text": "Impeller speed at least 150 rpm.",
            "value": {"type": "range", "min": 150.0, "max": None, "unit": "rpm"},
            "value_citation": {
                "doc": "URS-GR901",
                "rev": 0,
                "page": 1,
                "quote": "Impeller speed at least 150 rpm.",
            },
            "coverage": "gap",
            "reason": "no FAT/SAT step addresses it",
        },
        "evidence": [],
        "sources": [],
    }
)
SOP = (
    "3. Signatures\n"
    "Every signature carries a name and a date. A vendor FAT protocol is approved by the"
    " site before it is executed.\n"
    "4. Duties\n"
    "In one document, the preparer must not approve it, the checker and the approver are"
    " different people, and the performer of a step is not its witness.\n"
)
VMP = (
    "Annex 1. Required documents: GR-901 – Granulator\n"
    "Doc no. Document type Stage\n"
    "URS-GR901 User requirement specification Design\n"
    "FAT-GR901 FAT protocol and report FAT\n"
    "OQ-GR901 OQ protocol OQ\n"
)
ASSESSMENT = (
    "Issue date 02/02/2026\n"
    "Area Relied on Activities\n"
    "Mechanical Yes Design and fabrication.\n"
    "Software No Control software.\n"
    "5. Conclusion\n"
)
USERS: dict[str, str] = {
    "segment": _page(URS, "URS-GR901"),
    "extract": json.dumps(
        {"id": "URS-GR901-002", "requirement": "Impeller speed at least 150 rpm."}
    )
    + "\n\n"
    + _page(URS, "URS-GR901"),
    "facts": _page(VENDOR, "FAT-GR901"),
    "link": LINK,
    "transport": LINK,
    "vendor_assessment": _document(ASSESSMENT, doc="VA-1"),
    "record": _page(VENDOR, "FAT-GR901"),
    "required_documents": _document(VMP, doc="VMP-9"),
    "site_rules": _document(SOP, doc="SOP-9"),
    "ai_review": "Documents given: FAT-GR901 rev 0.",
    "draft": DRAFT_WITH_VALUE,
}


def _ask(name: str, user: str) -> dict[str, Any]:
    (r,) = NoLLM().complete([Request(PROMPTS[name], user, "sha")])
    return json.loads(r.text)


def test_every_prompt_is_answered() -> None:
    assert set(USERS) == set(PROMPTS)


@pytest.mark.parametrize("name", sorted(PROMPTS))
def test_each_answer_follows_its_prompt_schema(name: str) -> None:
    prompt = PROMPTS[name]
    llm = NoLLM()
    requests = [Request(prompt, USERS[name], "a"), Request(prompt, "", "b")]
    answers = llm.complete(requests)
    assert len(answers) == 2
    for a in answers:
        assert (a.model, a.input_tokens, a.output_tokens) == (MODEL, 0, 0)
        assert _valid(json.loads(a.text), dict(prompt.schema)) == []


def test_answers_keep_request_order() -> None:
    first = _page("URS-GR901-007 No Noise at most 70 dBA.", "URS-GR901")
    second = _page("URS-GR901-008 No Mass at most 900 kg.", "URS-GR901")
    a, b = NoLLM().complete(
        [Request(PROMPTS["segment"], first, "a"), Request(PROMPTS["segment"], second, "b")]
    )
    assert json.loads(a.text)["requirements"][0]["id"] == "URS-GR901-007"
    assert json.loads(b.text)["requirements"][0]["id"] == "URS-GR901-008"


def test_an_unknown_prompt_raises() -> None:
    odd = Prompt("summarise", "Summarise.", {"type": "object"}, 100)
    with pytest.raises(ValueError, match="summarise"):
        NoLLM().complete([Request(odd, "text", "sha")])


def test_segment_lists_numbered_rows_without_the_critical_flag() -> None:
    rows = _ask("segment", USERS["segment"])["requirements"]
    assert [r["id"] for r in rows] == [f"URS-GR901-00{i}" for i in range(1, 5)]
    assert rows[1] == {
        "id": "URS-GR901-002",
        "text": "Impeller speed at least 150 rpm.",
        "quote": "URS-GR901-002 No Impeller speed at least 150 rpm.",
    }


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("The bowl volume is 20–80 L.", {"kind": "range", "min": 20, "max": 80, "unit": "L"}),
        ("Impeller speed at least 150 rpm.", {"kind": "range", "min": 150, "unit": "rpm"}),
        ("Kapasitas maksimal 1.200 kg/jam.", {"kind": "range", "max": 1200, "unit": "kg/h"}),
        ("Kekasaran Ra maksimal 0,4 µm.", {"kind": "range", "max": 0.4, "unit": "µm"}),
        ("The granulator has 2 choppers.", {"kind": "number", "number": 2, "unit": None}),
        (
            "Parts are made of SS 316L or Hastelloy.",
            {"kind": "one_of", "allowed": ["SS 316L", "Hastelloy"]},
        ),
        ("An operating manual is available.", {"kind": "present"}),
        ("Certificate 3.1 is available.", {"kind": "present"}),
    ],
)
def test_extract_reads_the_value_from_the_requirement(text: str, expected: dict[str, Any]) -> None:
    user = json.dumps({"id": "R-1", "requirement": text}) + "\n\n" + _page(text)
    got = _ask("extract", user)
    assert {k: got[k] for k in expected} == expected
    assert got["quote"] == text


def test_facts_read_steps_dates_and_design_rows() -> None:
    got = _ask("facts", USERS["facts"])
    assert got["site_approved_on"]["date"] == "03-Mar-2026"
    assert got["executed_on"]["date"] == "05-Mar-2026"
    sweep, speed = got["steps"]
    assert (sweep["acceptance"], sweep["observed"], sweep["value"]["kind"]) == (
        "20–80 L",
        "20–80 L",
        "range",
    )
    assert (speed["step"], speed["acceptance"], speed["observed"], speed["result"]) == (
        "FAT-02",
        "≥ 150 rpm",
        "162 rpm",
        "pass",
    )
    assert speed["value"]["unit"] == "rpm"
    rows = _ask("facts", _page("Bowl volume 600 L\nEmergency stop Yes\nFrame SS 304"))["rows"]
    assert [(r["name"], r["printed"], r["value"]["kind"]) for r in rows] == [
        ("Bowl volume", "600 L", "number"),
        ("Emergency stop", "Yes", "present"),
        ("Frame", "SS 304", "text"),
    ]


def test_link_proposes_the_steps_and_rows_that_share_the_most_words() -> None:
    got = _ask("link", LINK)
    assert got["steps"] == ["F/FAT-02"]
    assert got["rows"] == ["DS#p1.1"]
    assert got["area"] is None


def test_record_reads_signature_rows() -> None:
    sigs = _ask("record", USERS["record"])["signatures"]
    assert [(s["role"], s["name"], s["date"], s["site"], s["signed"]) for s in sigs] == [
        ("approved", "Ana Lima", "03-Mar-2026", True, True),
        ("executed", "Tom Berg", "05-Mar-2026", False, True),
    ]


def test_site_rules_are_found_by_keywords() -> None:
    rules = {r["rule"]: r["quote"] for r in _ask("site_rules", USERS["site_rules"])["rules"]}
    assert rules == {
        "signature_name_and_date": "Every signature carries a name and a date.",
        "vendor_protocol_approved_before_execution": "A vendor FAT protocol is approved by the"
        " site before it is executed.",
        "preparer_not_approver": "the preparer must not approve it",
        "checker_not_approver": "the checker and the approver are different people",
        "performer_not_witness": "and the performer of a step is not its witness.",
    }


def test_required_documents_are_read_from_the_annex() -> None:
    (annex,) = _ask("required_documents", USERS["required_documents"])["annexes"]
    assert annex["equipment"] == "GR-901"
    assert [(r["doc_id"], r["type"], r["stage"]) for r in annex["rows"]] == [
        ("URS-GR901", "urs", "design"),
        ("FAT-GR901", "fat", "FAT"),
        ("OQ-GR901", "oq_protocol", "OQ"),
    ]


def test_vendor_assessment_reads_rated_areas() -> None:
    got = _ask("vendor_assessment", USERS["vendor_assessment"])
    assert got["assessed_on"]["date"] == "02/02/2026"
    assert [(a["area"], a["mark"], a["relied"]) for a in got["areas"]] == [
        ("Mechanical", "Yes", True),
        ("Software", "No", False),
    ]


def test_ai_review_finds_nothing() -> None:
    assert _ask("ai_review", USERS["ai_review"]) == {"findings": []}


def test_draft_copies_the_requirement_value_with_its_quote() -> None:
    got = _ask("draft", DRAFT_WITH_VALUE)
    assert got["acceptance"]["kind"] == "range"
    assert (got["acceptance"]["min"], got["acceptance"]["unit"]) == (150.0, "rpm")
    assert got["acceptance_source"] == {
        "doc": "URS-GR901",
        "rev": 0,
        "page": 1,
        "quote": "Impeller speed at least 150 rpm.",
    }


def test_draft_without_a_quoted_value_leaves_the_ac_to_a_human() -> None:
    request = json.loads(DRAFT_WITH_VALUE)
    request["requirement"]["value"] = None
    request["requirement"]["value_citation"] = None
    got = _ask("draft", json.dumps(request))
    assert got["acceptance"]["kind"] == "none"
    assert got["acceptance_source"] is None


def test_no_llm_cannot_run_live(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    code = main(["run", str(tmp_path), "--llm", "no-llm", "--live"])
    assert code == 2
    assert "--live" in capsys.readouterr().err


def test_no_llm_cannot_read_a_review_package(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """The baseline answers only the Equipment prompts, so a Review Package run (spec #196)
    refuses it before reading anything."""
    package = ["--review-package", str(tmp_path), "--package-recordings", str(tmp_path / "p")]
    code = main(["run", str(tmp_path), "--llm", "no-llm", *package])
    assert code == 2
    assert "runs alone" in capsys.readouterr().err


def test_the_baseline_scores_its_pinned_tp201_figures(tmp_path: Path) -> None:
    """The figures of ``recordings/README.md`` ("No-LLM baseline"), at tolerance 0. They are
    a comparison point, not a ratchet baseline: ``baselines/TP-201.json`` stays r10's."""
    args = ["run", str(MANIFEST), "--equipment", "TP-201", "--out", str(tmp_path)]
    assert main([*args, "--recordings", str(RECORDINGS), "--llm", "no-llm"]) == 0
    (folder,) = tmp_path.iterdir()
    meta = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    assert meta["model"] == MODEL
    assert meta["calls"] == {"total": 0, "replayed": 0, "live": 0}
    assert (meta["cost_usd"], meta["tokens"]) == (0, {"input": 0, "output": 0})

    sub = Submission.model_validate_json((folder / "submission.json").read_text("utf-8"))
    assert sub.system.model == MODEL
    world = PageTexts(build_corpus(load(ROOT / "world" / "tp201.yaml")))
    got = score(sub, load_key(ROOT / "answer_key" / "TP-201"), world)

    headline = {k: (v["k"], v["n"]) for k, v in got["headline"].items()}
    assert headline == {
        "requirements.value_accuracy": (33, 38),
        "citations.verified_rate": (107, 107),
        "defects.recall": (4, 7),
        "fabrication.rate": (0, 157),
        "probes.fabrication_rate": (0, 6),
        "ocr.exact_match_rate": (35, 36),
        "ocr.entry_recall": (36, 36),
        "ocr.cer": (4, 371),
    }
    assert got["gates"]["passed"] is True
    req = got["requirements"]["metrics"]
    assert (req["coverage_accuracy"], req["evidence_precision"], req["evidence_recall"]) == (
        round(13 / 38, 4),
        round(11 / 12, 4),
        round(7 / 14, 4),
    )
    defects = got["defects"]["metrics"]
    assert (defects["findings"], defects["false_positives"]) == (4, 0)
    documents = got["documents"]["metrics"]
    assert (documents["expected_missing"], documents["flagged"], documents["precision"]) == (
        2,
        2,
        1.0,
    )
