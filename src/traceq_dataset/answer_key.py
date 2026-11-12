"""Answer key derived from world data and the rendered corpus (design section 6).

Nothing here is written by hand. World data supplies the facts (requirements, Evidence,
the expected finding of each planted scenario, the documents the VMP requires); the corpus
supplies where they ended up (page, printed text, and the skewed quad of handwritten
entries on a scan). Layer and default reference of a finding follow from its type
(design section 7, taxonomy).

Files, one directory per Equipment (``answer_key/TP-201/``):

- ``requirements.yaml``: each requirement with its location, normalised value, its row in
  the risk assessment (Critical Aspect and scores), Evidence per step, design facts, and
  expected Coverage with the decision-table reason;
- ``defects.yaml``: the defect manifest, one entry per scenario with a finding;
- ``ambiguous.yaml``: values whose expected answer is "ask for confirmation";
- ``probes.yaml``: hallucination probes, facts the corpus does not hold, whose expected
  answer is "not found", with the lures beside them;
- ``documents.yaml``: documents that should exist, and why any is not in the corpus;
- ``ocr.yaml``: every handwritten entry on a scan with its quad.

The committed key is for the eval corpus (T0 2026-06-01, seed 0); CI re-derives it and
checks it against freshly rendered documents (``validate.answer_key_problems``).

Usage::

    uv run python -m traceq_dataset.answer_key world/tp201.yaml [--out answer_key] [--check]
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml
from openpyxl.utils.cell import coordinate_from_string
from pydantic import BaseModel

from traceq_dataset.corpus import Corpus, DocKey, build_corpus
from traceq_dataset.coverage import classify, meets, step_failure
from traceq_dataset.render import design_field
from traceq_dataset.schema import Anchor, DefectType, Equipment, Requirement, Scenario
from traceq_dataset.validate import normalise, page_texts

FILES = (
    "requirements.yaml",
    "defects.yaml",
    "ambiguous.yaml",
    "probes.yaml",
    "documents.yaml",
    "ocr.yaml",
)

Layer = str
TAXONOMY: Mapping[DefectType, tuple[Layer, str]] = {
    # type: (layer, default reference; primary first, "; " between equivalents)
    DefectType.MISSING_SIGNATURE: ("rule", "CPOB Ch. 10"),
    DefectType.IMPOSSIBLE_DATE_ORDER: ("rule", "CPOB Ch. 12"),
    DefectType.SEGREGATION_OF_DUTIES: ("rule", "SOP"),
    DefectType.OUT_OF_LIMIT_MARKED_PASS: ("rule", "CPOB 12.16"),
    DefectType.FAILED_RESULT_NO_DEVIATION: ("rule", "CPOB 12.16"),
    DefectType.AC_CHANGED_WITHOUT_DEVIATION: ("rule+llm", "CPOB 12.15"),
    DefectType.VENDOR_PROTOCOL_NOT_APPROVED: ("rule", "CPOB 12.14"),
    DefectType.EXPIRED_CALIBRATION: ("rule", "CPOB Ch. 12"),
    DefectType.CALCULATION_ERROR: ("rule", ""),
    DefectType.WATER_USED_IN_PHASE_1: ("rule", "WHO TRS 1033 Annex 3 §11.3"),
    DefectType.MISSING_ATTACHMENT: ("rule+llm", "CPOB Ch. 10"),
    DefectType.OUTDATED_REFERENCE: ("llm", ""),
    DefectType.INCONSISTENT_DATA: ("llm", ""),
    DefectType.AC_DEVIATES_FROM_URS: ("llm", ""),
    DefectType.GDP_CORRECTION: ("vision", "CPOB 10.8; PIC/S PI 041-1 §8.7"),
    DefectType.LEFTOVER_FROM_OTHER_EQUIPMENT: ("llm", ""),
    DefectType.DESIGN_CONFLICT: ("llm", ""),
    DefectType.AMBIGUOUS_VALUE: ("llm", ""),
}
"""Design section 7: layer and reference per defect type."""

QUAD_DECIMALS = 2


class AnswerKeyError(ValueError):
    """World data and corpus do not give a complete answer key."""


# --- Building blocks ----------------------------------------------------------------


def _plain(value: Any) -> Any:
    """JSON-like data with whole floats as ints (``20.0`` -> ``20``) and no Nones."""
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json", exclude_none=True)
    if isinstance(value, Mapping):
        return {k: _plain(v) for k, v in value.items() if v is not None}
    if isinstance(value, list | tuple):
        return [_plain(v) for v in value]
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _reference(text: str) -> dict[str, Any] | None:
    parts = [p.strip() for p in text.split(";") if p.strip()]
    return {"primary": parts[0], "equivalents": parts[1:]} if parts else None


def _quad(corpus: Corpus, doc: DocKey, key: str) -> list[list[float]] | None:
    scanned = corpus.scanned.get(doc)
    quad = scanned.placed[key].quad if scanned else None
    return [[round(x, QUAD_DECIMALS), round(y, QUAD_DECIMALS)] for x, y in quad] if quad else None


def locate(corpus: Corpus, anchor: Anchor, texts: dict[DocKey, list[str]]) -> dict[str, Any]:
    """Page, text and (on a scan) quad of an anchor; ``status: planned`` if not rendered."""
    doc = (anchor.doc, anchor.rev)
    loc: dict[str, Any] = {"doc": anchor.doc, "rev": anchor.rev}
    if doc not in corpus.rendered:
        return {**loc, "status": "planned"}
    rendered = corpus.rendered[doc]
    if anchor.field is not None:
        if anchor.field not in rendered.placed:
            raise AnswerKeyError(f"{rendered.filename}: no placed string {anchor.field!r}")
        placed = rendered.placed[anchor.field]
        loc |= {"page": placed.page, "field": anchor.field, "text": placed.text}
        quad = _quad(corpus, doc, anchor.field)
        return loc | ({"quad": quad} if quad else {})
    if rendered.format != "pdf":
        raise AnswerKeyError(f"{rendered.filename}: a text anchor needs a PDF")
    pages = texts.setdefault(doc, page_texts(rendered.pdf))
    wanted = normalise(anchor.text or "")
    found = [i for i, t in enumerate(pages, 1) if wanted in t]
    if not found:
        raise AnswerKeyError(f"{rendered.filename}: text {anchor.text!r} not found")
    return loc | {"page": found[0], "text": anchor.text}


# --- Files --------------------------------------------------------------------------


def requirements(corpus: Corpus) -> list[dict[str, Any]]:
    eq = corpus.eq
    urs = f"URS-{eq.tag.replace('-', '')}"
    revs = sorted(d.rev for d in eq.documents if d.id == urs)
    if not revs:
        raise AnswerKeyError(f"{eq.tag}: no {urs} rendered")
    protocols = {p.doc_id: p for p in eq.protocols}
    vendors = {eq.vendor.id: eq.vendor}
    out = []
    for r in eq.requirements:
        current = corpus.rendered[(urs, revs[-1])].placed[r.id]
        result = classify(r, eq.tests, eq.designs, protocols, vendors)
        entry: dict[str, Any] = {
            "id": r.id,
            "text": current.text,
            "source": {"doc": urs, "rev": revs[-1], "page": current.page, "section": r.section},
            "param": r.param,
            "value": _plain(r.spec),
            "critical": r.critical,
        }
        superseded = [
            {
                "rev": rev,
                "page": old.page,
                "text": old.text,
                "value": _plain(r.superseded_spec or r.spec),
            }
            for rev in revs[:-1]
            if (old := corpus.rendered[(urs, rev)].placed[r.id]).text != current.text
        ]
        if superseded:
            entry["superseded"] = superseded
        risk = _risk(corpus, r)
        if risk:
            entry["risk"] = risk
        entry["evidence"] = _test_evidence(corpus, r)
        entry["design_evidence"] = _design_evidence(corpus, r)
        entry |= {
            "expected_coverage": str(result.coverage),
            "reason": result.reason,
            "also_valid": [str(c) for c in r.also_valid],
        }
        out.append(entry)
    return out


def _risk(corpus: Corpus, r: Requirement) -> dict[str, Any] | None:
    """The requirement's FMEA row in the rendered risk assessment: where it is, whether it
    marks a Critical Aspect, and its scores."""
    ra = corpus.eq.risk_assessment
    if ra is None or (ra.doc_id, 0) not in corpus.rendered:
        return None
    row = next(x for x in ra.rows if x.requirement == r.id)
    placed = corpus.rendered[(ra.doc_id, 0)].placed[f"{r.id}.critical"]
    assert placed.cell is not None
    return {
        "doc": ra.doc_id,
        "rev": 0,
        "sheet": placed.sheet,
        "row": coordinate_from_string(placed.cell)[1],
        "text": placed.text,
        "critical": ra.critical(row),
        "severity": row.severity,
        "occurrence": row.occurrence,
        "detection": row.detection,
        "rpn": row.rpn,
    }


def _test_evidence(corpus: Corpus, r: Requirement) -> list[dict[str, Any]]:
    eq = corpus.eq
    protocols = {p.doc_id: p for p in eq.protocols}
    out = []
    for t in eq.tests:
        if t.requirement != r.id:
            continue
        doc = (t.protocol, 0)
        placed = corpus.rendered[doc].placed
        observed = placed[f"{t.step}.observed"]
        failure = step_failure(r, t, protocols[t.protocol], eq.vendor)
        entry: dict[str, Any] = {
            "doc": t.protocol,
            "rev": 0,
            "page": observed.page,
            "step": t.step,
            "acceptance": placed[f"{t.step}.acceptance"].text,
            "observed": observed.text,
            "value": _plain(t.observed),
            "recorded_result": t.recorded_result,
            "qualifies": failure is None,
        }
        if failure:
            entry["failure"] = failure
        if t.correction:
            entry["corrected_from"] = _plain(t.correction.original)
        quad = _quad(corpus, doc, f"{t.step}.observed")
        if quad:
            entry["quad"] = quad
        out.append(entry)
    return out


def _design_evidence(corpus: Corpus, r: Requirement) -> list[dict[str, Any]]:
    """Design facts with where the renderer placed them (``status: planned`` while their
    document is not rendered). A certificate row also names its part."""
    out = []
    for d in corpus.eq.designs:
        if d.requirement != r.id:
            continue
        entry: dict[str, Any] = {"doc": d.doc_id, "rev": 0}
        field = design_field(corpus.eq, d)
        if field is None:
            entry["status"] = "planned"
        else:
            placed = corpus.rendered[(d.doc_id, 0)].placed[field]
            entry |= {"page": placed.page, "field": field, "text": placed.text}
            if corpus.document((d.doc_id, 0)).type == "material_certificate":
                entry["part"] = d.label
        out.append(entry | {"value": _plain(d.observed), "meets_urs": meets(r.spec, d.observed)})
    return out


def defects(corpus: Corpus) -> list[dict[str, Any]]:
    eq, texts = corpus.eq, {}
    out = []
    for n, s in enumerate((s for s in eq.scenarios if s.finding), 1):
        f = s.finding
        assert f is not None
        layer, default_reference = TAXONOMY[f.type]
        locations = [locate(corpus, a, texts) for a in f.at]
        docs = {(a.doc, a.rev): None for a in f.at}
        out.append(
            {
                "id": f"D-{eq.tag.replace('-', '')}-{n:03d}",
                "scenario": s.id,
                "type": str(f.type),
                "severity": f.severity,
                "layer": layer,
                "reference": _reference(s.reference or default_reference),
                "detail": f.detail,
                "documents": [{"doc": d, "rev": rev} for d, rev in docs],
                "locations": locations,
            }
        )
    return out


_GROUPED = re.compile(r"(\d{1,3})([.,])(\d{3})(?:\s+(.+))?")


def readings(text: str) -> list[dict[str, Any]]:
    """Both readings of ``1.500 rpm``: thousands separator or decimal separator."""
    m = _GROUPED.fullmatch(text.strip())
    if not m:
        raise AnswerKeyError(f"{text!r} is not an ambiguous grouped number")
    head, sep, tail, unit = m.groups()
    grouping = "id" if sep == "." else "en"  # language whose thousands separator is `sep`
    out = [
        {"value": int(head + tail), "separator": "thousands", "convention": grouping},
        {
            "value": _plain(float(f"{head}.{tail}")),
            "separator": "decimal",
            "convention": "en" if grouping == "id" else "id",
        },
    ]
    return [r | {"unit": unit} for r in out] if unit else out


def ambiguous(corpus: Corpus) -> list[dict[str, Any]]:
    eq, texts = corpus.eq, {}
    tests = {t.step: t for t in eq.tests}
    reqs = {r.id: r for r in eq.requirements}
    out = []
    for s in eq.scenarios:
        if not s.finding or s.finding.type is not DefectType.AMBIGUOUS_VALUE:
            continue
        for a in s.finding.at:
            step = (a.field or "").removesuffix(".observed")
            if step not in tests:
                raise AnswerKeyError(f"{s.id}: ambiguous anchor must be a step's observed value")
            t = tests[step]
            loc = locate(corpus, a, texts)
            out.append(
                {
                    "id": f"A-{eq.tag.replace('-', '')}-{len(out) + 1:03d}",
                    "scenario": s.id,
                    "location": loc,
                    "readings": readings(loc["text"]),
                    "true_value": _plain(t.observed),
                    "requirement": t.requirement,
                    "requirement_value": _plain(reqs[t.requirement].spec),
                    "expected_answer": "ask_confirmation",
                }
            )
    return out


def probes(corpus: Corpus) -> list[dict[str, Any]]:
    """Hallucination probes: the requirement, what the corpus does not hold (``absent``),
    where the lures are, and for an ``acceptance`` probe the Acceptance Criteria a drafted
    Test Step may carry without making one up."""
    eq, texts = corpus.eq, {}
    reqs = {r.id: r for r in eq.requirements}
    urs = f"URS-{eq.tag.replace('-', '')}"
    rev = max(d.rev for d in eq.documents if d.id == urs)
    out = []
    for n, p in enumerate(eq.probes, 1):
        r = reqs[p.requirement]
        placed = corpus.rendered[(urs, rev)].placed[r.id]
        entry: dict[str, Any] = {
            "id": f"P-{eq.tag.replace('-', '')}-{n:03d}",
            "probe": p.id,
            "absent": p.absent,
            "requirement": r.id,
            "source": {"doc": urs, "rev": rev, "page": placed.page},
            "detail": p.detail,
            "lures": [locate(corpus, a, texts) for a in p.lures],
            "expected_answer": "not_found",
        }
        if p.absent == "acceptance":
            # An empty AC ("to be set by a human") or the URS value copied from its sentence.
            entry["accepted_acceptance"] = [None, _plain(r.spec)]
        out.append(entry)
    return out


def documents(corpus: Corpus) -> list[dict[str, Any]]:
    eq = corpus.eq
    if not eq.required_documents:
        raise AnswerKeyError(f"{eq.tag}: no required_documents in world data")
    out = []
    for d in eq.required_documents:
        entry: dict[str, Any] = {"id": d.id, "type": d.type, "stage": d.stage}
        entry["status"] = d.missing or "in_corpus"
        if d.missing is None:
            entry["files"] = [
                {"rev": rev, "file": corpus.filename((i, rev))}
                for i, rev in corpus.rendered
                if i == d.id
            ]
        if d.note:
            entry["note"] = d.note
        out.append(entry)
    return out


def ocr(corpus: Corpus) -> list[dict[str, Any]]:
    out = []
    for (doc, rev), scan in corpus.scanned.items():
        out.append(
            {
                "doc": doc,
                "rev": rev,
                "file": scan.filename,
                "dpi": scan.dpi,
                "level": scan.level,
                "skew": [round(a, 4) for a in scan.skew],
                "entries": [
                    {
                        "field": k,
                        "page": p.page,
                        "text": p.text,
                        "quad": _quad(corpus, (doc, rev), k),
                    }
                    for k, p in scan.placed.items()
                    if p.quad
                ],
            }
        )
    return out


def derive(corpus: Corpus) -> dict[str, list[dict[str, Any]]]:
    """Every answer-key file of one Equipment, keyed by file name."""
    built = {
        "requirements.yaml": requirements(corpus),
        "defects.yaml": defects(corpus),
        "ambiguous.yaml": ambiguous(corpus),
        "probes.yaml": probes(corpus),
        "documents.yaml": documents(corpus),
        "ocr.yaml": ocr(corpus),
    }
    assert tuple(built) == FILES
    return built


def scenarios_without_answer(eq: Equipment, key: Mapping[str, list[dict]]) -> list[Scenario]:
    """Scenarios the key does not mention: neither a finding nor a superseded value."""
    found = {d["scenario"] for d in key["defects.yaml"]}
    superseded = {r["id"] for r in key["requirements.yaml"] if "superseded" in r}
    return [s for s in eq.scenarios if s.id not in found and not set(s.targets) & superseded]


# --- Files on disk ------------------------------------------------------------------


def dump(name: str, data: list[dict[str, Any]], corpus: Corpus) -> str:
    header = (
        f"# {corpus.eq.tag} answer key: {name}. Generated, do not edit:\n"
        "#   uv run python -m traceq_dataset.answer_key world/<file>.yaml\n"
        f"# Corpus T0 {corpus.t0.isoformat()}, seed {corpus.seed}. "
        "Never sent to an LLM (design section 6).\n"
    )
    body = yaml.safe_dump(
        data, allow_unicode=True, sort_keys=False, width=100, default_flow_style=None
    )
    return header + body


def load_key(directory: Path) -> dict[str, list[dict[str, Any]]]:
    return {n: yaml.safe_load((directory / n).read_text(encoding="utf-8")) for n in FILES}


def main(argv: list[str]) -> int:
    from traceq_dataset.validate import answer_key_problems
    from traceq_dataset.world import load

    parser = argparse.ArgumentParser(prog="traceq_dataset.answer_key")
    parser.add_argument("world", type=Path)
    parser.add_argument("--out", type=Path, default=Path("answer_key"))
    parser.add_argument("--check", action="store_true", help="fail if the files are stale")
    args = parser.parse_args(argv)

    eq = load(args.world)
    corpus = build_corpus(eq)
    directory = args.out / eq.tag
    stale = []
    for name, data in derive(corpus).items():
        text, path = dump(name, data, corpus), directory / name
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                stale.append(str(path))
        else:
            directory.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
            print(f"{path}  ({len(data)} entries)")
    problems = answer_key_problems(load_key(directory), corpus) if directory.exists() else []
    for p in [*(f"stale: {s}" for s in stale), *problems]:
        print(p)
    return 1 if stale or problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
