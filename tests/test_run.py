"""``traceq run`` end to end (spec #29, primary seam): a released corpus in, a run folder out,
the submission scored by the real scorer. The LLM is a scripted fake; nothing is sent."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from traceq.ai import BudgetExceeded, PriceTable, Request, Response
from traceq.ai.cost import Price
from traceq.documents import OcrUnavailable, pdf
from traceq.runs import cli
from traceq.runs.api import create_app
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
# Test steps the scripted model reads: step -> (AC and observed as printed, value).
PRESENT = ("Present and functional", "Present and functional")
STEPS: dict[str, tuple[str, str, dict[str, Any]]] = {
    "FAT-M-01": (
        "≥ 36 stations",
        "36 stations",
        {"kind": "number", "number": 36, "unit": "stations"},
    ),
    "FAT-M-02": ("20–60 rpm", "20–60 rpm", {"kind": "range", "min": 20, "max": 60, "unit": "rpm"}),
    "FAT-M-03": ("≥ 100 kN", "96 kN", {"kind": "number", "number": 96, "unit": "kN"}),
    "FAT-M-12": (*PRESENT, {"kind": "present", "present": True}),
    "FAT-C-01": (*PRESENT, {"kind": "present", "present": True}),
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
            "acceptance": acceptance,
            "observed": observed,
            "result": "pass",
            "value": BLANK_VALUE | value,
            "quote": m[0],
        }
        for sid, (acceptance, observed, value) in STEPS.items()
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


# --- Pre-review: the scripted model reads signature rows, the VMP annex and the SOP ------

SIGNATURE = re.compile(
    r"^(?P<role>(?P<r>Prepared|Checked|Approved|Executed|Witnessed) by)"
    r"(?: (?P<name>\w+ \w+) (?P<org>.*?) Signed electronically (?P<date>\S+))?$"
)
ROLES = {"Prepared": "prepared", "Checked": "checked", "Approved": "approved"}
ROLES |= {"Executed": "executed", "Witnessed": "witnessed"}


def _record(r: Request) -> dict[str, Any]:
    signatures = [
        {
            "role_printed": m["role"],
            "role": ROLES[m["r"]],
            "site": "(site)" in (m["org"] or ""),
            "name": m["name"] or "",
            "signed": m["name"] is not None,
            "date": m["date"] or "",
            "quote": m[0],
        }
        for line in _page(r).splitlines()
        if (m := SIGNATURE.match(line))
    ]
    empty: list[Any] = []
    return {
        "signatures": signatures,
        "instruments": empty,
        "step_instruments": empty,
        "deviations": empty,
        "calculations": empty,
    }


def _pages(r: Request) -> dict[int, str]:
    return {int(m[1]): m[2] for m in re.finditer(r'<page n="(\d+)">\n(.*?)\n</page>', r.user, re.S)}


TYPES = {label: code for code, label in render.DOC_TYPES_ID.items()}
STAGES = {label: code for code, label in render.STAGES_ID.items()}
# Not printed in the VMP: the citation check must drop it, so it is never reported missing.
FABRICATED_ROW = {"doc_id": "PQ-TP201", "type_printed": "Protokol PQ", "stage_printed": "OQ"}


def _row(page: int, line: str) -> dict[str, Any] | None:
    for label, code in TYPES.items():
        m = re.match(rf"^(\S+-\S+) ({re.escape(label)}.*) (\w+)$", line)
        if m and m[3] in STAGES:
            return {
                "doc_id": m[1],
                "type_printed": m[2],
                "type": code,
                "stage_printed": m[3],
                "stage": STAGES[m[3]],
                "page": page,
                "quote": line,
            }
    return None


def _required(r: Request) -> dict[str, Any]:
    pages = _pages(r)
    head = next((n, x) for n, t in pages.items() for x in t.splitlines() if "Lampiran 1" in x)
    rows = [row for n, t in pages.items() for x in t.splitlines() if (row := _row(n, x))]
    fabricated = FABRICATED_ROW | {"type": "other", "stage": "OQ", "page": 2}
    fabricated["quote"] = "PQ-TP201 Protokol PQ OQ"
    return {
        "annexes": [
            {"equipment": "TP-201", "page": head[0], "quote": head[1], "rows": [*rows, fabricated]}
        ]
    }


SOP_RULES = {
    "signature_name_and_date": "Setiap tanda tangan disertai nama dan tanggal.",
    "vendor_protocol_approved_before_execution": (
        "Protokol FAT/SAT vendor diperiksa dan disetujui site sebelum dieksekusi."
    ),
    "preparer_not_approver": "penyusun tidak boleh menyetujui dokumen yang disusunnya",
    "checker_not_approver": "pemeriksa dan penyetuju adalah dua orang yang berbeda",
    "performer_not_witness": "pelaksana tidak boleh sekaligus menjadi Saksi",
}


def _site_rules(r: Request) -> dict[str, Any]:
    return {"rules": [{"rule": k, "page": 1, "quote": q} for k, q in SOP_RULES.items()]}


# --- AI Findings: the scripted model reports S3 and S1, and two it cannot cite ------------

DOCUMENT = re.compile(
    r'<document doc="([^"]+)" rev="(\d+)" type="[^"]+">\n(.*?)\n</document>', re.S
)
# Not printed anywhere: the citation check must drop the finding.
INVENTED_REFERENCE = "FAT-TP201-M refers to URS-TP201 rev 0."


def _lines(r: Request, pattern: str) -> list[dict[str, Any]]:
    """Every printed line matching ``pattern``, as a citation of the page it is on."""
    return [
        {"doc": m[1], "rev": int(m[2]), "page": n, "quote": hit[0]}
        for m in DOCUMENT.finditer(r.user)
        for n, text in _pages(Request(r.prompt, m[3], r.doc_sha256)).items()
        if (hit := re.search(pattern, text, re.M))
    ]


def _ai_review(r: Request) -> dict[str, Any]:
    serials = _lines(r, r"RTP36-25-04\d\d")
    sat = next(c for c in _lines(r, r"122\.400 tablets/h") if c["doc"] == "SAT-TP201")
    invented = {"doc": "FAT-TP201-M", "rev": 0, "page": 1, "quote": INVENTED_REFERENCE}
    superseded = {"doc": "URS-TP201", "rev": 0, "page": 1, "quote": "URS-TP201"}
    return {
        "findings": [
            {
                "type": "inconsistent_data",
                "detail": "The SAT serial number differs from the FAT and the datasheet.",
                "citations": serials,
            },
            {
                "type": "gdp_correction",
                "detail": "SAT-01 output is overwritten without initials, date or reason.",
                "citations": [sat],
            },
            {"type": "outdated_reference", "detail": "Old URS.", "citations": [invented]},
            {"type": "outdated_reference", "detail": "Old URS.", "citations": [superseded]},
        ]
    }


REVIEW = {
    "record": _record,
    "required_documents": _required,
    "site_rules": _site_rules,
    "ai_review": _ai_review,
}


# --- Drafting: the scripted model copies the verified URS value, or tries to invent one ---

NO_AC: dict[str, Any] = {"kind": "none", "min": None, "max": None, "number": None}
NO_AC |= {"unit": None, "allowed": [], "text": None}
# Requirement -> (proposed AC, its source), each emptied by the AC validator.
UNSOURCED: dict[str, tuple[dict[str, Any], dict[str, Any] | None]] = {
    # Probe P6: no document names the lubricant class.
    "URS-TP201-013": (NO_AC | {"kind": "text", "text": "H1"}, None),
    # Probe P5: a stopping time from a page the model was not given.
    "URS-TP201-018": (
        NO_AC | {"kind": "number", "number": 2, "unit": "s"},
        {"doc": "SAT-TP201", "rev": 0, "page": 1, "quote": "Press each emergency stop"},
    ),
    # The URS sentence is cited (filled in below), but it does not state 5 kN.
    "URS-TP201-003": (NO_AC | {"kind": "number", "number": 5, "unit": "kN"}, None),
    # A quote that is not on the page.
    "URS-TP201-005": (
        NO_AC | {"kind": "range", "min": 50, "unit": "kN"},
        {"doc": "URS-TP201", "rev": 1, "page": 1, "quote": FABRICATED_QUOTE},
    ),
}


def _ac(value: dict[str, Any]) -> dict[str, Any]:
    ac = NO_AC | {"kind": value["type"]}
    for k, v in value.items():
        if k == "value":
            ac["number" if value["type"] == "number" else "text"] = v
        elif k != "type":
            ac[k] = v
    return ac


def _draft(r: Request) -> dict[str, Any]:
    asked = json.loads(r.user)
    req = asked["requirement"]
    ac, source = NO_AC, None
    if req["id"] in UNSOURCED:
        ac, source = UNSOURCED[req["id"]]
        if req["id"] == "URS-TP201-003":
            urs = asked["sources"][0]
            line = next(x for x in urs["text"].splitlines() if x.startswith(req["id"]))
            source = {k: urs[k] for k in ("doc", "rev", "page")} | {"quote": line}
    elif req["value"] is not None:
        ac, source = _ac(req["value"]), req["value_citation"]
    return {
        "description": f"Verify {req['id']}",
        "method": "Operate the press across its range and record the reading.",
        "instrument": "calibrated tachometer",
        "acceptance": ac,
        "acceptance_source": source,
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
        if r.prompt.name == "draft":
            return json.dumps(_draft(r))
        if r.prompt.name in REVIEW:
            return json.dumps(REVIEW[r.prompt.name](r))
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


def test_the_api_serves_the_run_and_opens_each_cited_page(
    recorded: RunOutput, corpus_dir: Path
) -> None:
    """The read-only API over a real run folder: the matrix as written, and every citation
    opens a document of the released corpus."""
    client = TestClient(create_app(recorded.folder.parent, corpus_dir))
    run_id = recorded.folder.name

    assert [r["run_id"] for r in client.get("/runs").json()] == [run_id]
    served = client.get(f"/runs/{run_id}/matrix").json()
    assert served == json.loads((recorded.folder / "matrix.json").read_text(encoding="utf-8"))
    cited = {
        (c["doc"], c["rev"])
        for row in served["requirements"]
        for c in [row["source"]] + [e["citation"] for e in row["evidence"] + row["design"]]
    }
    assert len(cited) > 1
    for doc, rev in sorted(cited):
        r = client.get(f"/runs/{run_id}/documents/{doc}/{rev}")
        assert r.status_code == 200, (doc, rev)


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
        ("required_document", "PQ-TP201"),
        *(("acceptance", rid) for rid in UNSOURCED),
        ("ai_finding", "outdated_reference 3"),
        ("ai_finding", "outdated_reference 4"),
    }
    assert FABRICATED_STEP["quote"] not in text


def _report(recorded: RunOutput) -> dict[str, Any]:
    sub = Submission.model_validate_json(
        (recorded.folder / "submission.json").read_text(encoding="utf-8")
    )
    return score(sub, load_key(KEY), PageTexts(build_corpus(load(TP201))))


def test_check_findings_match_the_planted_rule_defects(recorded: RunOutput) -> None:
    """S4 and S5 are on born-digital FATs; S2 is on scans, which this slice does not read
    yet (its rule is tested on its facts in ``test_review_units``)."""
    report = _report(recorded)
    found = {d["scenario"]: d["found_by"] for d in report["defects"]["items"]}
    assert found["S4"] and found["S5"]
    metrics = report["defects"]["metrics"]
    assert (metrics["false_positives"], metrics["mislabelled"]) == (0, 0)
    assert report["citations"]["by_status"]["verified"] == report["citations"]["total"]

    review = json.loads((recorded.folder / "findings.json").read_text(encoding="utf-8"))
    by_type = {f["type"]: f for f in review["check_findings"]}
    assert set(by_type) == {"vendor_protocol_not_approved", "out_of_limit_marked_pass"}
    assert all(f["layer"] == "check" for f in review["check_findings"])
    s4 = by_type["vendor_protocol_not_approved"]
    assert s4["doc"] == "FAT-TP201-C" and [c["quote"] for c in s4["citations"]] == ["Approved by"]
    # A site rule cites the SOP sentence that sets it.
    assert s4["rule"]["doc"] == "SOP-VAL-002"
    assert s4["rule"]["quote"] == SOP_RULES["vendor_protocol_approved_before_execution"]
    assert {r["rule"] for r in review["site_rules"]} == set(SOP_RULES)


def test_ai_findings_are_cited_kept_apart_and_scored_in_their_layer(
    recorded: RunOutput,
) -> None:
    """S3 (inconsistent serial number) and S1 (GDP correction on the SAT scan) come from the
    AI layer; the scorer counts them under the layers the answer key gives them."""
    report = _report(recorded)
    found = {d["scenario"]: d["found_by"] for d in report["defects"]["items"]}
    assert found["S1"] and found["S3"]
    recall = report["defects"]["metrics"]["recall_by_layer"]
    assert (recall["llm"], recall["vision"], recall["rule"]) == (
        round(1 / 3, 4),
        1.0,
        round(2 / 3, 4),
    )
    assert report["gates"]["passed"], report["gates"]

    review = json.loads((recorded.folder / "findings.json").read_text(encoding="utf-8"))
    ai = {f["type"]: f for f in review["ai_findings"]}
    assert set(ai) == {"inconsistent_data", "gdp_correction"}
    assert {f["type"] for f in review["check_findings"]}.isdisjoint(ai)
    serial = ai["inconsistent_data"]
    assert {"SAT-TP201", "FAT-TP201-M", "DS-TP201"} <= {c["doc"] for c in serial["citations"]}
    assert serial["sources"] == [{"doc": c["doc"], "rev": c["rev"]} for c in serial["citations"]]
    for f in ai.values():
        assert f["layer"] == "ai" and f["reviewer_action"] == "pending"
        assert (f["model"], f["prompt"], f["created"]) == (
            MODEL,
            recorded.metadata["prompts"]["ai_review"],
            recorded.metadata["created"],
        )
    text = (recorded.folder / "submission.json").read_text(encoding="utf-8")
    assert INVENTED_REFERENCE not in text and "outdated_reference" not in text


def test_missing_documents_are_what_the_vmp_requires_and_the_corpus_lacks(
    recorded: RunOutput,
) -> None:
    report = _report(recorded)
    metrics = report["documents"]["metrics"]
    assert (metrics["precision"], metrics["recall"]) == (1.0, 1.0)
    assert metrics["flagged_but_in_corpus"] == []

    sub = json.loads((recorded.folder / "submission.json").read_text(encoding="utf-8"))
    assert sub["missing_documents"] == [
        {"type": "iq_protocol", "stage": "IQ", "id": "IQ-TP201"},
        {"type": "oq_protocol", "stage": "OQ", "id": "OQ-TP201"},
    ]
    review = json.loads((recorded.folder / "findings.json").read_text(encoding="utf-8"))
    required = review["required_documents"]
    assert len(required) == 14 and all(r["citation"]["doc"] == "VMP-001" for r in required)
    assert [r["doc_id"] for r in required if not r["in_corpus"]] == ["IQ-TP201", "OQ-TP201"]
    # The site-wide VMP and SOP are not on the list; a row the VMP does not print is dropped.
    assert not {"VMP-001", "SOP-VAL-002", "PQ-TP201"} & {r["doc_id"] for r in required}
    oq = next(r for r in review["missing_documents"] if r["doc_id"] == "OQ-TP201")
    assert oq["citation"]["page"] == 2 and "Protokol OQ" in oq["citation"]["quote"]


def test_run_metadata_records_model_prompts_tokens_and_cost(recorded: RunOutput) -> None:
    meta = json.loads((recorded.folder / "run.json").read_text(encoding="utf-8"))
    assert meta["model"] == MODEL
    assert meta["mode"] == "live"
    assert set(meta["prompts"]) == {
        "segment",
        "extract",
        "facts",
        "link",
        "record",
        "required_documents",
        "site_rules",
        "ai_review",
        "draft",
    }
    assert all(re.fullmatch(r"[0-9a-f]{64}", h) for h in meta["prompts"].values())
    # One segmentation call per URS page, one extraction and one link per requirement, one
    # fact call per page of FAT-TP201-M (2), FAT-TP201-C (1), SAT-TP201 (2, a scan),
    # DS-TP201 (1) and MTC-TP201-01 (1, a scan); one record call per page of the FATs (3),
    # the SAT (2) and the three calibration certificates (3, scans); one call each for the
    # VMP and the SOP; one AI review over the current documents; one draft per requirement
    # the vendor did not cover (all 38: no Vendor Assessment is read yet).
    calls = 2 + 38 + 38 + 7 + 8 + 2 + 1 + 38
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
        # Read by the AI review only, which reads every current document.
        ("RA-TP201", 0),
        ("DS-TP201", 0),
        ("DQ-TP201", 0),
        ("FDS-TP201", 0),
        ("MTC-TP201-01", 0),
        ("KAL-2025-0412", 0),
        ("KAL-2026-0057", 0),
        ("CAL-TP201-01", 0),
        ("VMP-001", 3),
        ("SOP-VAL-002", 2),
        ("VA-2025-011", 0),
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
    assert {d["format"] for d in meta["ingest"]} == {"born_digital", "scan", "xlsx"}
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


# --- Drafted Test Steps -------------------------------------------------------------------

DETERMINISTIC = ("traces_to_requirement", "ac_sourced_or_empty")


def test_drafted_steps_pass_scorer_criteria_1_and_2(recorded: RunOutput) -> None:
    """Criterion 1 fails only where the key expects ``covered_by_vendor``: without a Vendor
    Assessment (#55) the run cannot show condition 1, so it drafts those too."""
    report = _report(recorded)
    steps = report["test_steps"]
    rates = steps["metrics"]["criteria_pass_rate"]
    assert rates["ac_sourced_or_empty"] == 1.0
    not_scored = {c: v for c, v in rates.items() if c not in DETERMINISTIC}
    assert len(not_scored) == 4 and set(not_scored.values()) == {"not_scored"}
    key = {r["id"]: r["expected_coverage"] for r in load_key(KEY)["requirements.yaml"]}
    failing = {
        i["requirement"] for i in steps["items"] if not i["criteria"]["traces_to_requirement"]
    }
    assert failing == {rid for rid, c in key.items() if c == "covered_by_vendor"}
    assert steps["metrics"]["site_test_recall"] == 1.0
    assert report["gates"]["fabricated_acceptance_criterion"]["count"] == 0
    acceptance = [p for p in report["probes"]["items"] if p["absent"] == "acceptance"]
    assert [p["status"] for p in acceptance] == ["not_found", "not_found"]


def test_an_ac_is_copied_from_a_verified_citation_or_left_for_a_human(
    recorded: RunOutput,
) -> None:
    sub = json.loads((recorded.folder / "submission.json").read_text(encoding="utf-8"))
    steps = {s["requirement"]: s for s in sub["test_steps"]}
    assert len(steps) == 38
    speed = steps["URS-TP201-002"]
    assert speed["acceptance"] == {"type": "range", "min": 20, "max": 70, "unit": "rpm"}
    assert speed["acceptance_citation"]["doc"] == "URS-TP201"
    assert "70 rpm" in speed["acceptance_citation"]["quote"]
    for rid in UNSOURCED:
        assert "acceptance" not in steps[rid] and "acceptance_citation" not in steps[rid], rid

    drafts = json.loads((recorded.folder / "drafts.json").read_text(encoding="utf-8"))
    assert drafts["vendor_reuse"] is True
    flags = {d["requirement"]: d["acceptance_flag"] for d in drafts["test_steps"]}
    human = "to be set by a human"
    assert flags["URS-TP201-013"] == f"{human}: no source cited"
    assert flags["URS-TP201-018"] == f"{human}: source not given"
    assert flags["URS-TP201-003"] == f"{human}: value not in the quote"
    assert flags["URS-TP201-005"] == f"{human}: quote not on the page"
    assert flags["URS-TP201-002"] is None


def test_each_draft_is_an_ai_finding_pending_review(recorded: RunOutput) -> None:
    drafts = json.loads((recorded.folder / "drafts.json").read_text(encoding="utf-8"))
    meta = recorded.metadata
    assert len(drafts["test_steps"]) == 38
    for d in drafts["test_steps"]:
        assert d["layer"] == "ai"
        assert d["reviewer_action"] == "pending"
        assert d["source"] == {"doc": "URS-TP201", "rev": 1}
        assert (d["model"], d["prompt"], d["created"]) == (
            MODEL,
            meta["prompts"]["draft"],
            meta["created"],
        )
        assert d["saved_by_reuse"] is False


def test_vendor_reuse_is_a_run_setting_recorded_in_the_run(
    recorded: RunOutput, corpus_dir: Path, tmp_path: Path, seeded: Callable[[Path], Path]
) -> None:
    """Eval runs keep the default, true: scorer criterion 1 assumes it."""
    assert recorded.metadata["settings"] == {"vendor_reuse": True}
    seeded(tmp_path / "rec")
    out = run(
        corpus_dir,
        tmp_path / "runs",
        tmp_path / "rec",
        MODEL,
        live=ScriptedLLM(),
        prices=PRICES,
        vendor_reuse=False,
    )
    assert out.metadata["settings"] == {"vendor_reuse": False}
    drafts = json.loads((out.folder / "drafts.json").read_text(encoding="utf-8"))
    assert drafts["vendor_reuse"] is False
    assert len(out.submission.test_steps) == len(out.submission.requirements) == 38
