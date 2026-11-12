"""Eval report: ``report.json`` (everything, for the baseline and ratchet) and
``report.md`` (the summary a PR links to)."""

from __future__ import annotations

import hashlib
import json
from importlib.metadata import version
from pathlib import Path
from typing import Any

from traceq_dataset.answer_key import FILES
from traceq_dataset.corpus import Corpus
from traceq_eval.submission import Submission


def key_sha256(directory: Path) -> str:
    """One hash over the answer-key files, so a report names the exact key it used."""
    h = hashlib.sha256()
    for name in FILES:
        h.update(name.encode())
        h.update((directory / name).read_bytes())
    return h.hexdigest()


def with_metadata(
    report: dict[str, Any], sub: Submission, corpus: Corpus, key_dir: Path
) -> dict[str, Any]:
    return {
        "dataset": {
            "version": version("traceq-dataset"),
            "equipment": corpus.eq.tag,
            "t0": corpus.t0.isoformat(),
            "seed": corpus.seed,
            "answer_key_sha256": key_sha256(key_dir),
        },
        "submission": sub.system.model_dump(mode="json", exclude_none=True),
        **report,
    }


def _fmt(x: Any) -> str:
    if x is None:
        return "–"
    if isinstance(x, float):
        return f"{x:.3f}"
    if isinstance(x, list):
        return ", ".join(map(str, x)) or "–"
    if isinstance(x, dict):
        return "; ".join(f"{k} {_fmt(v)}" for k, v in x.items())
    return str(x)


def markdown(report: dict[str, Any]) -> str:
    ds, sub, gates = report.get("dataset", {}), report.get("submission", {}), report["gates"]
    out = [
        f"# Eval report: {report['equipment']}",
        "",
        f"- Submission: {_fmt(sub.get('name'))}, model {_fmt(sub.get('model'))}, "
        f"prompt {_fmt(sub.get('prompt'))}, run {_fmt(sub.get('run_id'))}",
        f"- Dataset {_fmt(ds.get('version'))}, T0 {_fmt(ds.get('t0'))}, "
        f"seed {_fmt(ds.get('seed'))}, answer key `{str(ds.get('answer_key_sha256', ''))[:12]}`; "
        f"scorer {report['scorer_version']}",
        "",
        f"## Gates: {'PASS' if gates['passed'] else 'FAIL'}",
        "",
        "| Gate (floor 0) | Count | |",
        "|---|---|---|",
    ]
    for name, g in gates.items():
        if name != "passed":
            out.append(f"| {name} | {g['count']} | {'pass' if g['passed'] else 'FAIL'} |")
    for name, g in gates.items():
        if name != "passed" and g["items"]:
            out += ["", f"{name}:", ""]
            out += [f"- `{json.dumps(i, ensure_ascii=False)}`" for i in g["items"][:20]]
    fab = report["fabrication"]
    out += [
        "",
        f"Fabrication rate: {_fmt(fab['rate'])} ({fab['fabricated']} of {fab['claims']} claims)",
    ]
    probes = report["probes"]["metrics"]
    out += [
        "",
        f"Probe fabrication rate: {_fmt(probes['fabrication_rate'])} "
        f"({probes['fabricated']} of {probes['probes']} hallucination probes)",
    ]
    out += [
        f"- {i['id']} ({i['requirement']}, {i['absent']}): {_fmt(i['claims'])}"
        for i in report["probes"]["items"]
        if i["status"] == "fabricated"
    ]
    for section in ("requirements", "defects", "ambiguous", "probes", "documents", "test_steps"):
        out += ["", f"## {section}", "", "| Metric | Value |", "|---|---|"]
        out += [f"| {k} | {_fmt(v)} |" for k, v in report[section]["metrics"].items()]
    cm = report["requirements"]["confusion"]
    cols = list(next(iter(cm.values())))
    out += ["", "Coverage confusion (rows expected, columns submitted):", ""]
    out += ["| | " + " | ".join(cols) + " |", "|---" * (len(cols) + 1) + "|"]
    out += [f"| {e} | " + " | ".join(str(row[c]) for c in cols) + " |" for e, row in cm.items()]
    cit = report["citations"]
    out += [
        "",
        "## citations",
        "",
        f"{cit['total']} citations, verified rate {_fmt(cit['verified_rate'])}: "
        + _fmt({k: v for k, v in cit["by_status"].items() if v}),
        "",
        f"Not scored: {_fmt(report['not_scored'])}",
        "",
    ]
    return "\n".join(out)


def write(report: dict[str, Any], out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    (out / "report.md").write_text(markdown(report), encoding="utf-8", newline="\n")
