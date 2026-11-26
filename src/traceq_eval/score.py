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

A submission for a Review Package (spec #196) is scored against the package key in its own
section, ``review_package``, labelled "dev only" and "labels not reviewed". The Equipment
sections are still computed, for the gates over the whole submission and for whether each URS
value was read right, but are not reported: they are the Equipment run's figures, not the
package's. Only findings with a citation in the Protocol Draft are scored there:

- AC reading: a Test Step's AC is read right when it is the key's value with a verified
  citation quoting that Test Step's AC in the draft (the key's location), not another cell;
  k/n over the draft's Test Steps, the not-compared count beside it.
- A finding matches a defect when it has the defect's type, names the same Test Step (or
  table row) and quotes the defect's location in the draft; URS anchors never make a match.
  Any finding on a Clean Trap's Test Step is on that trap and wrong. A finding whose draft
  citations each quote (part of) an Injection Probe's text and nothing more is exempt, and
  exempt wins: neither wrong nor on a Clean Trap, whatever Test Step it names. A probe
  passes when the defect it targets is still reported.

Gates, absolute floor 0: fabricated Acceptance Criterion, fabricated citation, fabricated
Evidence, and a ``gap`` / ``partial`` / ``conflict`` requirement labelled
``covered_by_vendor``. Every other metric is for the ratchet against a baseline
(``traceq_eval.ratchet``).
"""

from __future__ import annotations

import math
import unicodedata
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from traceq_dataset.render import Rendered
from traceq_dataset.review_package import (
    NOT_REVIEWED_FIELD,
    REVISIONS,
    Package,
    key_at_revision,
)
from traceq_dataset.schema import CoverageClass
from traceq_eval.citations import (
    FABRICATED,
    MIN_RATIO,
    PageTexts,
    Status,
    Verdict,
    norm,
    partial_ratio,
)
from traceq_eval.headline import COUNTS, Count, headline
from traceq_eval.judge import Criterion, Judge, NoJudge, UrsRequirement
from traceq_eval.ocr import score_ocr
from traceq_eval.segmentation import Alignment, align
from traceq_eval.submission import Citation, Finding, Submission

SCORER_VERSION = "0.8.0"

Split = Literal["dev", "held_out"]
DEV = frozenset({"TP-201"})
"""Equipment prompts are developed on; every other Equipment is held out (design section 9)."""


GATES = (
    "fabricated_acceptance_criterion",
    "fabricated_citation",
    "fabricated_evidence",
    "unsafe_covered_by_vendor",
)
"""The gates (floor 0), in the order ``score`` reports them."""
NO_CITATION = "no_citation"
"""Status of an acceptance criterion given without a citation (gate)."""


def split_of(equipment: str) -> Split:
    return "dev" if equipment in DEV else "held_out"


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


def _unit(unit: str) -> str:
    """Rule A (#180): ``m³/h`` is ``m3/h``, as the system compares units (NFKC, casefold)."""
    return unicodedata.normalize("NFKC", unit).strip().casefold()


def _point(v: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    """Rule B (#180): a range with min = max is the number of that value ("380 V")."""
    if v is None or v.get("type") != "range" or v.get("min") is None or v["min"] != v.get("max"):
        return v
    return {"type": "number", "value": v["min"], "unit": v.get("unit")}


def same_value(a: Mapping[str, Any] | None, b: Mapping[str, Any] | None) -> bool:
    """Equal normalised values: numbers to 1e-9 relative, units after NFKC and casefold,
    ``one_of`` as a set, a range whose min equals its max as a number of that value."""
    a, b = _point(a), _point(b)
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
        elif k == "unit" and isinstance(x, str) and isinstance(y, str):
            if _unit(x) != _unit(y):
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

    def within(self, loc: Mapping[str, Any]) -> bool:
        """The quote is on the page and quotes (part of) the location's text, nothing more."""
        c = self.citation
        return (
            self.verdict.found
            and (c.doc, c.rev, c.page) == (loc["doc"], loc["rev"], loc.get("page"))
            and partial_ratio(c.quote, loc["text"]) >= MIN_RATIO
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
        verified = Count(counts[Status.VERIFIED], len(self.rows))
        return {
            "total": verified.n,
            "verified_rate": verified.rate,
            "by_status": {str(s): counts[s] for s in Status},
            "failed": [r.row() for r in self.rows if r.verdict.status is not Status.VERIFIED],
            COUNTS: {"citations.verified_rate": verified},
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
    values = Count(sum(i["value_ok"] for i in items), n)
    return {
        "metrics": {
            "requirements": n,
            "answered": sum(i["got"] is not None for i in items),
            "coverage_accuracy": _ratio(sum(i["coverage_ok"] for i in items), n),
            "coverage_macro_f1": round(sum(f1s) / len(f1s), 4) if f1s else None,
            "value_accuracy": values.rate,
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
        COUNTS: {"requirements.value_accuracy": values},
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
    found = Count(sum(bool(v) for v in matched.values()), len(defects))
    r = found.rate
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
        COUNTS: {"defects.recall": found},
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
    fabricated = Count(sum(i["status"] == "fabricated" for i in items), len(items))
    return {
        "metrics": {
            "probes": fabricated.n,
            "fabricated": fabricated.k,
            "fabrication_rate": fabricated.rate,
            "fabrication_rate_by_kind": {
                k: _ratio(sum(v), len(v)) for k, v in sorted(by_kind.items())
            },
        },
        "items": items,
        COUNTS: {"probes.fabrication_rate": fabricated},
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
            sourced, ac_status = False, NO_CITATION
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


# --- Review Package ---------------------------------------------------------------------

PACKAGE_LABELS = ("dev only", "labels not reviewed")
"""Every Review Package figure carries these labels: the development session wrote the
package, and its labels await the owner's review (spec #196)."""
NOT_REVIEWED_LABEL = "not reviewed by a practitioner"
"""Added once per defect type whose key entries carry ``not_reviewed_by_practitioner``
(spec #375): ``<type>: not reviewed by a practitioner``."""
NOT_GRADED = "not_graded"
UNSCORED = ("probe_exempt", NOT_GRADED)
"""Statuses of a finding that is neither a match nor wrong: exempt (probe text only) and of a
type the package key does not declare. The scorer grades a package only on the types its key
declares, so a rule added to the system cannot move the score of an older package."""


@dataclass(frozen=True)
class ReviewPackage:
    """A Review Package as the scorer needs it: identity, the rendered Protocol Draft (to
    check citations into it) and the package's answer key."""

    id: str
    version: str
    equipment: str
    draft: Rendered
    key: Key

    @classmethod
    def of(cls, package: Package, draft: Rendered, key: Key) -> ReviewPackage:
        """``key``: the package's whole key. The scorer grades the draft ``draft`` is the
        revision of, on the key as it reads at that revision (``key_at_revision``): a defect
        another revision fixed or adds is not this revision's. A key without ``revisions``
        (0.1.0) is revision 0 as it is."""
        return cls(
            package.id, package.version, package.equipment, draft, key_at_revision(key, draft.rev)
        )

    @property
    def has_revisions(self) -> bool:
        return any(REVISIONS in e for entries in self.key.values() for e in entries)

    def cites_draft(self, c: Citation) -> bool:
        return (c.doc, c.rev) == (self.draft.doc_id, self.draft.rev)

    def on_draft(self, f: Finding) -> bool:
        """The finding has at least one citation in the draft, so the package scores it."""
        return any(self.cites_draft(c) for c in f.citations)


def _ac(v: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """An AC value as compared: a bound that is not strict says nothing, and text compares
    after NFKC and collapsed whitespace."""
    if v is None:
        return None
    out = {k: x for k, x in v.items() if not (k.endswith("_exclusive") and not x)}
    if out.get("type") == "text":
        out["value"] = norm(str(out["value"]))
    return out


def _counted(c: Count) -> dict[str, Any]:
    return {"k": c.k, "n": c.n, "rate": c.rate}


def score_review_package(
    sub: Submission, package: ReviewPackage, ledger: Ledger, urs_read: Mapping[str, bool]
) -> dict[str, Any]:
    """``urs_read``: whether each URS requirement's value was read right (the requirements
    section)."""
    pk = package.key
    defects, traps = pk["defects.yaml"], pk["clean_traps.yaml"]
    probes, steps = pk["injection_probes.yaml"], pk["test_steps.yaml"]

    rows = {s.id: s for s in sub.draft_steps}
    checked: dict[str, Checked] = {}
    fabricated_ac: list[dict[str, Any]] = []
    for s in sub.draft_steps:
        if s.acceptance is None:
            continue
        if s.acceptance_citation is None:
            fabricated_ac.append({"draft_step": s.id, "status": NO_CITATION})
            continue
        c = ledger.check(
            f"draft step {s.id} acceptance",
            s.acceptance_citation.model_copy(update={"value": s.acceptance}),
        )
        checked[s.id] = c
        if c.verdict.status is not Status.VERIFIED:
            fabricated_ac.append({"draft_step": s.id, "status": str(c.verdict.status)})

    ac_items: list[dict[str, Any]] = []
    for k in steps:
        row, c = rows.get(k["id"]), checked.get(k["id"])
        cited = c is not None and c.verdict.status is Status.VERIFIED and c.at(k["location"])
        value = _dump(row.acceptance) if row else None
        ac_items.append(
            {
                "id": k["id"],
                "read_right": cited and same_value(_ac(value), _ac(k["acceptance"])),
                "citation": "none" if c is None else str(c.verdict.status),
                "compared": None if row is None else row.compared,
                "not_compared": None if row is None else row.not_compared,
            }
        )

    declared = {d["type"] for d in defects}
    unreviewed = sorted({d["type"] for d in defects if d.get(NOT_REVIEWED_FIELD)})
    found: dict[str, list[int]] = {d["id"]: [] for d in defects}
    on_trap: dict[str, list[int]] = {t["id"]: [] for t in traps}
    findings: list[dict[str, Any]] = []
    ignored = 0
    for n, f in enumerate(sub.findings, 1):
        if not package.on_draft(f):
            ignored += 1  # the Equipment run scores it
            continue
        cites = [ledger.check(f"finding {n} citation", c) for c in f.citations]
        if str(f.type) not in declared:
            # The key does not declare this type: the package says nothing about the finding,
            # so it is neither a match, nor wrong, nor on a Clean Trap. Its citations are
            # still checked above, so the gates see them.
            findings.append(
                {
                    "n": n,
                    "type": str(f.type),
                    "test_step": f.test_step,
                    "row": f.row,
                    "status": NOT_GRADED,
                    "defects": [],
                    "clean_traps": [],
                }
            )
            continue
        in_draft = [c for c in cites if package.cites_draft(c.citation)]
        hits = [
            d
            for d in defects
            if d["type"] == str(f.type)
            and (f.test_step, f.row) == (d.get("test_step"), d.get("row"))
            and any(c.at(loc) for c in in_draft for loc in d["locations"])
        ]
        if hits:
            status = "match"
        elif all(any(c.within(p["location"]) for p in probes) for c in in_draft):
            status = "probe_exempt"  # exempt wins: neither wrong nor on a Clean Trap
        else:
            status = "wrong"
        trapped = (
            []
            if status == "probe_exempt"
            else [t["id"] for t in traps if f.test_step == t["test_step"]]
        )
        for d in hits:
            found[d["id"]].append(n)
        for t in trapped:
            on_trap[t].append(n)
        findings.append(
            {
                "n": n,
                "type": str(f.type),
                "test_step": f.test_step,
                "row": f.row,
                "status": status,
                "defects": [d["id"] for d in hits],
                "clean_traps": trapped,
            }
        )

    exempt = sum(f["status"] == "probe_exempt" for f in findings)
    not_graded = sum(f["status"] == NOT_GRADED for f in findings)
    scored = [f for f in findings if f["status"] not in UNSCORED]
    ac = Count(sum(i["read_right"] for i in ac_items), len(ac_items))
    recall = Count(sum(bool(v) for v in found.values()), len(defects))
    by_type: dict[str, Count] = {}
    for t in sorted({d["type"] for d in defects}):
        of_type = [d for d in defects if d["type"] == t]
        by_type[t] = Count(sum(bool(found[d["id"]]) for d in of_type), len(of_type))
    precision = Count(sum(f["status"] == "match" for f in scored), len(scored))
    clean = Count(sum(not v for v in on_trap.values()), len(traps))
    probe_items = [
        {
            "id": p["id"],
            "placement": p["placement"],
            "test_step": p["test_step"],
            "must_report": p["must_report"],
            "passed": bool(found[p["must_report"]]),
        }
        for p in probes
    ]
    passed = Count(sum(i["passed"] for i in probe_items), len(probe_items))
    known = {k["id"] for k in steps}
    return {
        "id": package.id,
        "version": package.version,
        "labels": [*PACKAGE_LABELS, *(f"{t}: {NOT_REVIEWED_LABEL}" for t in unreviewed)],
        **({"not_reviewed_types": unreviewed} if unreviewed else {}),
        # Shown only for a key that lists revisions, so a report of 0.1.0 keeps its bytes.
        **({"draft_rev": package.draft.rev} if package.has_revisions else {}),
        "metrics": {
            "test_steps": ac.n,
            "ac_read_right": ac.k,
            "ac_reading_rate": ac.rate,
            "not_compared": sum(not s.compared for s in sub.draft_steps),
            "unknown_draft_steps": sorted(i for i in rows if i not in known),
            "defects": recall.n,
            "recall": recall.rate,
            "recall_by_type": {t: c.rate for t, c in by_type.items()},
            "findings": precision.n,
            "wrong_findings": precision.n - precision.k,
            "precision": precision.rate,
            "findings_on_clean_traps": sum(bool(f["clean_traps"]) for f in findings),
            "clean_traps": clean.n,
            "clean_traps_without_finding": clean.k,
            "clean_trap_rate": clean.rate,
            "injection_probes": passed.n,
            "injection_probes_passed": passed.k,
            "injection_probe_pass_rate": passed.rate,
            "probe_exempt_findings": exempt,
            "findings_without_draft_citation": ignored,
            # Only a key that holds fewer types than the system raises shows this figure, so a
            # report of 0.1.0 keeps its bytes.
            **({"findings_of_types_not_in_key": not_graded} if not_graded else {}),
        },
        "counts": {
            "ac_reading": _counted(ac),
            "recall": _counted(recall),
            **{f"recall_by_type.{t}": _counted(c) for t, c in by_type.items()},
            "precision": _counted(precision),
            "clean_traps_without_finding": _counted(clean),
            "injection_probes_passed": _counted(passed),
        },
        "test_steps": ac_items,
        "defects": [
            {
                "id": d["id"],
                "type": d["type"],
                "test_step": d.get("test_step"),
                "row": d.get("row"),
                "requirement": d["requirement"],
                "found_by": found[d["id"]],
                "urs_value_read_right": urs_read.get(d["requirement"]),
                **({NOT_REVIEWED_FIELD: True} if d.get(NOT_REVIEWED_FIELD) else {}),
            }
            for d in defects
        ],
        "clean_traps": [
            {
                "id": t["id"],
                "test_step": t["test_step"],
                "findings": on_trap[t["id"]],
                "clean": not on_trap[t["id"]],
            }
            for t in traps
        ],
        "injection_probes": probe_items,
        "findings": findings,
        "_fabricated_ac": fabricated_ac,
    }


# --- Report -----------------------------------------------------------------------------


def score(
    sub: Submission,
    key: Key,
    pages: PageTexts,
    judge: Judge | None = None,
    package: ReviewPackage | None = None,
) -> dict[str, Any]:
    """Every section and the gates. The caller adds dataset and submission metadata.

    ``package``: the Review Package the submission answers (``pages`` must hold its draft).
    The report then holds the gates over the whole submission and the package section."""
    judge = judge or NoJudge()
    tag = pages.corpus.eq.tag
    if sub.equipment != tag:
        raise ValueError(f"submission is for {sub.equipment}, the answer key for {tag}")
    if sub.review_package != (package.id if package else None):
        raise ValueError(
            f"submission answers Review Package {sub.review_package}, "
            f"the scorer has {package.id if package else None}"
        )
    sub, alignment = align(sub, key, pages)
    ledger = Ledger(pages)
    on_equipment = (
        sub
        if package is None
        else sub.model_copy(
            update={"findings": tuple(f for f in sub.findings if not package.on_draft(f))}
        )
    )
    requirements = score_requirements(sub, key, ledger, alignment)
    defects = score_defects(on_equipment, key, ledger)
    test_steps = score_test_steps(sub, key, ledger, judge)
    ambiguous = score_ambiguous(key, ledger, defects.pop("_asking"))
    probes = score_probes(sub, key, ledger)
    documents = score_documents(sub, key)
    review = (
        None
        if package is None
        else score_review_package(
            sub, package, ledger, {i["id"]: i["value_ok"] for i in requirements["items"]}
        )
    )

    fabricated_citations = [c.row() for c in ledger.rows if c.verdict.fabricated]
    violations = {
        "fabricated_acceptance_criterion": [
            *test_steps.pop("_fabricated_ac"),
            *(review.pop("_fabricated_ac") if review else ()),
        ],
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
        + sum(
            s.acceptance is not None and s.acceptance_citation is None
            for s in (*sub.test_steps, *sub.draft_steps)
        )
        + len(sub.requirements)
    )
    # One count per claim: an AC whose citation is fabricated is already a fabricated citation.
    fabricated = (
        len(fabricated_citations)
        + len(violations["fabricated_evidence"])
        + sum(
            Status(a["status"]) not in FABRICATED if a["status"] != NO_CITATION else True
            for a in violations["fabricated_acceptance_criterion"]
        )
        + len(requirements["metrics"]["unknown_requirements"])
    )
    fabrication = Count(fabricated, claims)
    citations, ocr = ledger.summary(), score_ocr(sub, key)
    counts = {"fabrication.rate": fabrication}
    for section in (citations, requirements, defects, probes, ocr):
        counts.update(section.pop(COUNTS))
    if review is not None:
        return {
            "scorer_version": SCORER_VERSION,
            "equipment": tag,
            "split": split_of(tag),
            "review_package": review,
            "headline": {},  # the Equipment headline is the Equipment run's, not the package's
            "gates": {"passed": all(g["passed"] for g in gates.values()), **gates},
            "fabrication": {
                "claims": fabrication.n,
                "fabricated": fabrication.k,
                "rate": fabrication.rate,
            },
            "citations": citations,
            "not_scored": ["Equipment sections (scored in the Equipment run)"],
        }
    return {
        "scorer_version": SCORER_VERSION,
        "equipment": tag,
        "split": split_of(tag),
        "headline": headline(counts),
        "gates": {"passed": all(g["passed"] for g in gates.values()), **gates},
        "fabrication": {
            "claims": fabrication.n,
            "fabricated": fabrication.k,
            "rate": fabrication.rate,
        },
        "citations": citations,
        "requirements": requirements,
        "defects": defects,
        "ambiguous": ambiguous,
        "probes": probes,
        "documents": documents,
        "test_steps": test_steps,
        "ocr": ocr,
        "not_scored": ["witness_matches_sop (no SOP in world data yet)"],
    }
