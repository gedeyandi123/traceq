"""Score a submission against an Equipment's answer key (design section 9). Deterministic.

One report section per answer-key file, plus the citations every claim carries and the
gates.

- ``requirements``: Coverage class (``also_valid`` counts as correct), extracted value, the
  rev 0 value of a superseded requirement (S8), citation of the URS sentence, and the vendor
  steps offered as Evidence. Answers are paired with requirements by id when the URS prints
  its requirement numbers, otherwise by the URS text they quote (``traceq_eval.segmentation``).
- ``defects``: a finding matches a planted defect when it has the defect's type and one of
  its citations quotes one of the defect's locations (same document, revision and page, the
  location's text inside the quote). Recall per defect, layer and severity; precision per
  finding; false positives on clean documents. An ``ambiguous_value`` finding that matches no
  defect of that type is left out here: asking is scored in ``ambiguous`` only.
- ``ambiguous``: whether each ambiguous value was raised for confirmation, or a value was
  silently claimed from it.
- ``probes``: hallucination probes, facts the corpus does not hold. A probe rides on a
  requirement or a drafted Test Step the submission answers anyway, so the right answer is
  to claim nothing: for ``absent: evidence``, no Evidence step, no ``covered_by_vendor`` or
  ``partial`` class and no citation that fails its check; for ``absent: acceptance``, every
  drafted Test Step of the requirement leaves its AC empty or copies the URS value. Anything
  else is a fabricated answer. The probe fabrication rate is reported on its own, not as a
  gate (design section 9).
- ``documents``: documents that should exist but are not in the corpus, matched by type and
  stage.
- ``ocr``: handwritten entries on scans, read by the submission (``traceq_eval.ocr``): entry
  recall, localisation, exact match and CER, by kind and scan level. Not a gate.
- ``test_steps``: drafted Test Steps on the deterministic criteria (1 traces to a requirement
  that needs site testing, 2 AC sourced or left empty; 6 needs the SOP, which world data does
  not have yet) and, through a ``Judge``, criteria 3–5.

Gates, absolute floor 0: fabricated Acceptance Criterion, fabricated citation, fabricated
Evidence, and a ``gap`` / ``partial`` / ``conflict`` requirement labelled
``covered_by_vendor``. Every other metric is for the ratchet against a baseline
(``traceq_eval.ratchet``).
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from traceq_dataset.schema import CoverageClass
from traceq_eval.citations import (
    FABRICATED,
    MIN_RATIO,
    PageTexts,
    Status,
    Verdict,
    partial_ratio,
)
from traceq_eval.judge import Criterion, Judge, NoJudge, UrsRequirement
from traceq_eval.ocr import score_ocr
from traceq_eval.segmentation import Alignment, align
from traceq_eval.submission import Citation, Submission

SCORER_VERSION = "0.5.0"

CLAIMS_A_TEST = frozenset({"covered_by_vendor", "partial"})
"""Coverage classes that say a vendor step tested the requirement."""
UNSAFE_IF_COVERED = frozenset({"gap", "partial", "conflict"})
"""Expected classes that must never be labelled ``covered_by_vendor`` (gate)."""
NEEDS_SITE_TEST = frozenset({"partial", "gap", "site_only"})
"""Expected classes the drafted IQ/OQ must test. A ``conflict`` is resolved by the vendor
or a Change Control first; a step tracing to one is allowed but not required."""

Key = Mapping[str, list[dict[str, Any]]]

CRITERIA = (
    "traces_to_requirement",  # 1, deterministic
    "ac_sourced_or_empty",  # 2, deterministic
    "witness_matches_sop",  # 6, deterministic once world data has the SOP
    *(str(c) for c in Criterion),  # 3-5, LLM judge
)
"""The six criteria of a drafted Test Step (design section 9)."""


def _dump(model: Any) -> dict[str, Any] | None:
    return None if model is None else model.model_dump(mode="json", exclude_none=True)


def _ratio(n: int, d: int) -> float | None:
    """``None`` when there is nothing to measure, so an empty denominator is not a score."""
    return round(n / d, 4) if d else None


def _f1(p: float | None, r: float | None) -> float | None:
    """0 when nothing expected was found (also when nothing was predicted at all)."""
    if r == 0 or p == 0:
        return 0.0
    if p is None or r is None:
        return None
    return round(2 * p * r / (p + r), 4)


def same_value(a: Mapping[str, Any] | None, b: Mapping[str, Any] | None) -> bool:
    """Equal normalised values: numbers to 1e-9 relative, ``one_of`` as a set."""
    if a is None or b is None or a.get("type") != b.get("type"):
        return False
    for k in set(a) | set(b):
        x, y = a.get(k), b.get(k)
        if k == "allowed":
            if set(x or ()) != set(y or ()):
                return False
        elif isinstance(x, int | float) and isinstance(y, int | float):
            if not math.isclose(x, y, rel_tol=1e-9, abs_tol=1e-9):
                return False
        elif isinstance(x, str) and isinstance(y, str):
            if x.strip() != y.strip():
                return False
        elif x != y:
            return False
    return True


# --- Citation ledger --------------------------------------------------------------------


@dataclass(frozen=True)
class Checked:
    where: str
    citation: Citation
    verdict: Verdict

    def at(self, loc: Mapping[str, Any]) -> bool:
        """The quote is on the page and quotes the location's text."""
        c = self.citation
        return (
            self.verdict.found
            and (c.doc, c.rev, c.page) == (loc["doc"], loc["rev"], loc.get("page"))
            and partial_ratio(loc["text"], c.quote) >= MIN_RATIO
        )

    def row(self) -> dict[str, Any]:
        c = self.citation
        return {
            "where": self.where,
            "doc": c.doc,
            "rev": c.rev,
            "page": c.page,
            "quote": c.quote,
            "status": str(self.verdict.status),
            "ratio": round(self.verdict.ratio, 4),
        }


@dataclass
class Ledger:
    """Every citation of the submission, checked once."""

    pages: PageTexts
    rows: list[Checked] = field(default_factory=list)

    def check(self, where: str, c: Citation) -> Checked:
        verdict = self.pages.check(c.doc, c.rev, c.page, c.quote, _dump(c.value))
        checked = Checked(where, c, verdict)
        self.rows.append(checked)
        return checked

    def summary(self) -> dict[str, Any]:
        counts = Counter(str(r.verdict.status) for r in self.rows)
        return {
            "total": len(self.rows),
            "verified_rate": _ratio(counts[Status.VERIFIED], len(self.rows)),
            "by_status": {str(s): counts[s] for s in Status},
            "failed": [r.row() for r in self.rows if r.verdict.status is not Status.VERIFIED],
        }


# --- Sections ---------------------------------------------------------------------------


def score_requirements(
    sub: Submission, key: Key, ledger: Ledger, alignment: Alignment | None = None
) -> dict[str, Any]:
    """``alignment``: how answers were paired with requirements by span (``None``: by id)."""
    answers = {a.id: a for a in sub.requirements}
    steps = {(t.protocol, 0, t.step) for t in ledger.pages.corpus.eq.tests}
    classes = [str(c) for c in CoverageClass]
    confusion = {e: dict.fromkeys([*classes, "missing"], 0) for e in classes}
    items, unsafe, fabricated_evidence = [], [], []
    ev_submitted = ev_right = ev_needed = ev_found = 0
    for r in key["requirements.yaml"]:
        a = answers.get(r["id"])
        expected, valid = r["expected_coverage"], {r["expected_coverage"], *r["also_valid"]}
        got = str(a.coverage) if a and a.coverage else None
        graded: str = got if got is not None and got in valid else expected
        confusion[graded][got or "missing"] += 1
        if got == "covered_by_vendor" and expected in UNSAFE_IF_COVERED and got not in valid:
            unsafe.append({"requirement": r["id"], "expected": expected, "got": got})

        value = _dump(a.value) if a else None
        superseded = [old["value"] for old in r.get("superseded", [])]
        src = r["source"]
        cites = [ledger.check(f"{r['id']} citation", c) for c in (a.citations if a else ())]
        source_cited = any(
            c.verdict.status is Status.VERIFIED
            and (c.citation.doc, c.citation.rev, c.citation.page)
            == (src["doc"], src["rev"], src["page"])
            for c in cites
        )

        key_ev = {(e["doc"], e["rev"], e["step"]) for e in r["evidence"]}
        qualifying = {(e["doc"], e["rev"], e["step"]) for e in r["evidence"] if e["qualifies"]}
        sub_ev = {(e.doc, e.rev, e.step) for e in (a.evidence if a else ())}
        for e in sorted(sub_ev - steps):
            fabricated_evidence.append(
                {"requirement": r["id"], "doc": e[0], "rev": e[1], "step": e[2]}
            )
        ev_submitted += len(sub_ev)
        ev_right += len(sub_ev & key_ev)
        if expected == "covered_by_vendor":
            ev_needed += len(qualifying)
            ev_found += len(sub_ev & qualifying)

        items.append(
            {
                "id": r["id"],
                "expected": expected,
                "got": got,
                "coverage_ok": got in valid,
                "value_ok": same_value(value, r["value"]),
                "superseded_value": any(same_value(value, v) for v in superseded)
                and not same_value(value, r["value"]),
                "source_cited": source_cited,
                "evidence_unknown_to_key": sorted("/".join(map(str, e)) for e in sub_ev - key_ev),
            }
        )

    known = {r["id"] for r in key["requirements.yaml"]}
    extra = set(alignment.extra) if alignment else set[str]()
    for a in sub.requirements:
        if a.id not in known:
            for c in a.citations:
                ledger.check(f"{a.id} citation", c)
            for e in a.evidence:
                if (e.doc, e.rev, e.step) not in steps:
                    fabricated_evidence.append(
                        {"requirement": a.id, "doc": e.doc, "rev": e.rev, "step": e.step}
                    )
    n = len(items)
    segmentation: dict[str, Any] = {}
    if alignment:
        matched = {m.requirement: m for m in alignment.matches}
        for i in items:
            m = matched.get(i["id"])
            if m:
                i.update(answer=m.answer, cover=m.cover, purity=m.purity)
        segmentation = {
            "segmentation_recall": _ratio(len(matched), alignment.requirements),
            "segmentation_precision": _ratio(len(matched), alignment.answers),
            "extra_segments": alignment.extra,
        }
    per_class = {}
    for c in classes:
        tp = confusion[c][c]
        predicted = sum(confusion[e][c] for e in classes)
        support = sum(confusion[c].values())
        p, rec = _ratio(tp, predicted), _ratio(tp, support)
        per_class[c] = {"precision": p, "recall": rec, "f1": _f1(p, rec), "support": support}
    f1s = [v["f1"] for v in per_class.values() if v["support"] and v["f1"] is not None]
    return {
        "metrics": {
            "requirements": n,
            "answered": sum(i["got"] is not None for i in items),
            "coverage_accuracy": _ratio(sum(i["coverage_ok"] for i in items), n),
            "coverage_macro_f1": round(sum(f1s) / len(f1s), 4) if f1s else None,
            "value_accuracy": _ratio(sum(i["value_ok"] for i in items), n),
            "superseded_values": sum(i["superseded_value"] for i in items),
            "source_citation_rate": _ratio(sum(i["source_cited"] for i in items), n),
            "evidence_precision": _ratio(ev_right, ev_submitted),
            "evidence_recall": _ratio(ev_found, ev_needed),
            "unknown_requirements": sorted(
                a.id for a in sub.requirements if a.id not in known and a.id not in extra
            ),
            **segmentation,
        },
        "per_class": per_class,
        "confusion": confusion,
        "items": items,
        "_unsafe": unsafe,
        "_fabricated_evidence": fabricated_evidence,
    }


def score_defects(sub: Submission, key: Key, ledger: Ledger) -> dict[str, Any]:
    defects = key["defects.yaml"]
    defect_docs = {(d["doc"], d["rev"]) for x in defects for d in x["documents"]}
    matched: dict[str, list[int]] = {d["id"]: [] for d in defects}
    findings, asking = [], []
    for n, f in enumerate(sub.findings, 1):
        cites = [ledger.check(f"finding {n} citation", c) for c in f.citations]
        if f.type == "ambiguous_value":
            asking += cites
        located = [
            d
            for d in defects
            if any(c.at(loc) for c in cites for loc in d["locations"] if "page" in loc)
        ]
        hits = [d for d in located if d["type"] == str(f.type)]
        if f.type == "ambiguous_value" and not hits:
            continue  # asking is scored in the ambiguous section, never as a wrong defect
        for d in hits:
            matched[d["id"]].append(n)
        if hits:
            status = "match"
        elif located:
            status = "mislabelled"
        else:
            status = "false_positive"
        docs = {(c.citation.doc, c.citation.rev) for c in cites}
        findings.append(
            {
                "n": n,
                "type": str(f.type),
                "severity": f.severity,
                "status": status,
                "defects": [d["id"] for d in hits] or [d["id"] for d in located],
                "on_clean_document": status == "false_positive" and not docs & defect_docs,
            }
        )

    def recall(group: str) -> dict[str, float | None]:
        out: dict[str, list[bool]] = {}
        for d in defects:
            out.setdefault(d[group], []).append(bool(matched[d["id"]]))
        return {k: _ratio(sum(v), len(v)) for k, v in sorted(out.items())}

    severity_pairs = [
        (f["severity"], d["severity"])
        for f in findings
        if f["status"] == "match"
        for d in defects
        if d["id"] in f["defects"]
    ]
    p = _ratio(sum(f["status"] == "match" for f in findings), len(findings))
    r = _ratio(sum(bool(v) for v in matched.values()), len(defects))
    return {
        "metrics": {
            "defects": len(defects),
            "findings": len(findings),
            "recall": r,
            "precision": p,
            "f1": _f1(p, r),
            "recall_by_layer": recall("layer"),
            "recall_by_severity": recall("severity"),
            "mislabelled": sum(f["status"] == "mislabelled" for f in findings),
            "false_positives": sum(f["status"] == "false_positive" for f in findings),
            "false_positives_on_clean_documents": sum(f["on_clean_document"] for f in findings),
            "severity_agreement": _ratio(
                sum(a == b for a, b in severity_pairs), len(severity_pairs)
            ),
        },
        "items": [
            {
                "id": d["id"],
                "scenario": d["scenario"],
                "type": d["type"],
                "found_by": matched[d["id"]],
            }
            for d in defects
        ],
        "findings": findings,
        "_asking": asking,
    }


def score_ambiguous(key: Key, ledger: Ledger, asking: list[Checked]) -> dict[str, Any]:
    """``asking``: citations of the submission's ``ambiguous_value`` findings."""
    items = []
    for a in key["ambiguous.yaml"]:
        loc = a["location"]
        claimed = [c.where for c in ledger.rows if c.citation.value is not None and c.at(loc)]
        items.append(
            {
                "id": a["id"],
                "asked": any(c.at(loc) for c in asking),
                "silently_resolved": sorted(set(claimed)),
            }
        )
    return {
        "metrics": {
            "ambiguous": len(items),
            "asked_rate": _ratio(sum(i["asked"] for i in items), len(items)),
            "silently_resolved": sum(bool(i["silently_resolved"]) for i in items),
        },
        "items": items,
    }


def score_probes(sub: Submission, key: Key, ledger: Ledger) -> dict[str, Any]:
    """Run after the requirements section, whose citations it reads from the ledger."""
    answers = {a.id: a for a in sub.requirements}
    items = []
    for p in key["probes.yaml"]:
        rid, claims = p["requirement"], []
        if p["absent"] == "evidence":
            a = answers.get(rid)
            claims += [f"evidence {e.doc}/{e.step}" for e in (a.evidence if a else ())]
            if a and a.coverage in CLAIMS_A_TEST:
                claims.append(f"coverage {a.coverage}")
            claims += [
                f"citation {c.citation.doc} p{c.citation.page} {c.verdict.status}"
                for c in ledger.rows
                if c.where == f"{rid} citation"
                and (c.verdict.fabricated or c.verdict.status is Status.VALUE_NOT_IN_QUOTE)
            ]
        else:
            accepted = p["accepted_acceptance"]
            claims += [
                f"step {s.id} acceptance {_dump(s.acceptance)}"
                for s in sub.test_steps
                if s.requirement == rid
                and s.acceptance is not None
                and not _copies(_dump(s.acceptance), accepted)
            ]
        items.append(
            {
                "id": p["id"],
                "absent": p["absent"],
                "requirement": rid,
                "status": "fabricated" if claims else "not_found",
                "claims": claims,
            }
        )
    by_kind: dict[str, list[bool]] = {}
    for i in items:
        by_kind.setdefault(i["absent"], []).append(i["status"] == "fabricated")
    fabricated = sum(i["status"] == "fabricated" for i in items)
    return {
        "metrics": {
            "probes": len(items),
            "fabricated": fabricated,
            "fabrication_rate": _ratio(fabricated, len(items)),
            "fabrication_rate_by_kind": {
                k: _ratio(sum(v), len(v)) for k, v in sorted(by_kind.items())
            },
        },
        "items": items,
    }


def _copies(ac: Mapping[str, Any] | None, accepted: list[Any]) -> bool:
    """The AC is one the key accepts; a ``present`` AC matches whether or not it states
    ``value: true``, since the URS sentence only says the feature must be there."""
    return any(
        v is not None
        and ac is not None
        and (same_value(ac, v) or ac["type"] == v["type"] == "present")
        for v in accepted
    )


def score_documents(sub: Submission, key: Key) -> dict[str, Any]:
    expected = Counter(
        (d["type"], d["stage"]) for d in key["documents.yaml"] if d["status"] != "in_corpus"
    )
    present = {(d["type"], d["stage"]) for d in key["documents.yaml"] if d["status"] == "in_corpus"}
    flagged = Counter((d.type, d.stage) for d in sub.missing_documents)
    hit = sum((expected & flagged).values())
    p, r = _ratio(hit, sum(flagged.values())), _ratio(hit, sum(expected.values()))
    return {
        "metrics": {
            "expected_missing": sum(expected.values()),
            "flagged": sum(flagged.values()),
            "precision": p,
            "recall": r,
            "f1": _f1(p, r),
            "flagged_but_in_corpus": sorted(f"{t}/{s}" for t, s in flagged if (t, s) in present),
        },
        "items": [
            {"type": t, "stage": s, "expected": expected[(t, s)], "flagged": flagged[(t, s)]}
            for t, s in sorted(set(expected) | set(flagged))
        ],
    }


def score_test_steps(sub: Submission, key: Key, ledger: Ledger, judge: Judge) -> dict[str, Any]:
    reqs = {r["id"]: r for r in key["requirements.yaml"]}
    items, fabricated_ac = [], []
    for s in sub.test_steps:
        r = reqs.get(s.requirement)
        traces = r is not None and r["expected_coverage"] != "covered_by_vendor"
        if s.acceptance is None:
            sourced, ac_status = True, "flagged_empty"
        elif s.acceptance_citation is None:
            sourced, ac_status = False, "no_citation"
        else:
            c = s.acceptance_citation
            checked = ledger.check(
                f"step {s.id} acceptance", c.model_copy(update={"value": s.acceptance})
            )
            sourced, ac_status = (
                checked.verdict.status is Status.VERIFIED,
                str(checked.verdict.status),
            )
        if not sourced:
            fabricated_ac.append({"step": s.id, "requirement": s.requirement, "status": ac_status})
        urs = UrsRequirement(r["id"], r["text"], r["value"]) if r else None
        judged = {}
        for criterion in Criterion:
            v = judge.judge(s, urs, criterion)
            judged[str(criterion)] = (
                None if v is None else {"passed": v.passed, "critique": v.critique}
            )
        items.append(
            {
                "id": s.id,
                "requirement": s.requirement,
                "criteria": {
                    "traces_to_requirement": traces,
                    "ac_sourced_or_empty": sourced,
                    "witness_matches_sop": None,
                    **{k: (None if v is None else v["passed"]) for k, v in judged.items()},
                },
                "ac_status": ac_status,
                "critiques": {k: v["critique"] for k, v in judged.items() if v},
            }
        )
    needed = sorted(i for i, r in reqs.items() if r["expected_coverage"] in NEEDS_SITE_TEST)
    tested = {s.requirement for s in sub.test_steps}
    pass_rates = {}
    for c in CRITERIA:
        scored = [i["criteria"][c] for i in items if i["criteria"][c] is not None]
        pass_rates[c] = _ratio(sum(scored), len(scored)) if scored else "not_scored"
    return {
        "metrics": {
            "steps": len(items),
            "requirements_needing_site_test": len(needed),
            "site_test_recall": _ratio(len(tested & set(needed)), len(needed)),
            "untested_requirements": [i for i in needed if i not in tested],
            "criteria_pass_rate": pass_rates,
            "judge": judge.name,
        },
        "items": items,
        "_fabricated_ac": fabricated_ac,
    }


# --- Report -----------------------------------------------------------------------------


def score(
    sub: Submission, key: Key, pages: PageTexts, judge: Judge | None = None
) -> dict[str, Any]:
    """Every section and the gates. The caller adds dataset and submission metadata."""
    judge = judge or NoJudge()
    tag = pages.corpus.eq.tag
    if sub.equipment != tag:
        raise ValueError(f"submission is for {sub.equipment}, the answer key for {tag}")
    sub, alignment = align(sub, key, pages)
    ledger = Ledger(pages)
    requirements = score_requirements(sub, key, ledger, alignment)
    defects = score_defects(sub, key, ledger)
    test_steps = score_test_steps(sub, key, ledger, judge)
    ambiguous = score_ambiguous(key, ledger, defects.pop("_asking"))
    probes = score_probes(sub, key, ledger)
    documents = score_documents(sub, key)

    fabricated_citations = [c.row() for c in ledger.rows if c.verdict.fabricated]
    violations = {
        "fabricated_acceptance_criterion": test_steps.pop("_fabricated_ac"),
        "fabricated_citation": fabricated_citations,
        "fabricated_evidence": requirements.pop("_fabricated_evidence"),
        "unsafe_covered_by_vendor": requirements.pop("_unsafe"),
    }
    gates = {
        name: {"count": len(items), "floor": 0, "passed": not items, "items": items}
        for name, items in violations.items()
    }
    claims = (
        len(ledger.rows)
        + sum(len(a.evidence) for a in sub.requirements)
        + sum(s.acceptance is not None and s.acceptance_citation is None for s in sub.test_steps)
        + len(sub.requirements)
    )
    # One count per claim: an AC whose citation is fabricated is already a fabricated citation.
    fabricated = (
        len(fabricated_citations)
        + len(violations["fabricated_evidence"])
        + sum(
            Status(a["status"]) not in FABRICATED if a["status"] != "no_citation" else True
            for a in violations["fabricated_acceptance_criterion"]
        )
        + len(requirements["metrics"]["unknown_requirements"])
    )
    return {
        "scorer_version": SCORER_VERSION,
        "equipment": tag,
        "gates": {"passed": all(g["passed"] for g in gates.values()), **gates},
        "fabrication": {
            "claims": claims,
            "fabricated": fabricated,
            "rate": _ratio(fabricated, claims),
        },
        "citations": ledger.summary(),
        "requirements": requirements,
        "defects": defects,
        "ambiguous": ambiguous,
        "probes": probes,
        "documents": documents,
        "test_steps": test_steps,
        "ocr": score_ocr(sub, key),
        "not_scored": ["witness_matches_sop (no SOP in world data yet)"],
    }
