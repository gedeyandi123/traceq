"""The TraceQ system must not see what it is scored against (design section 6, "Answer key").

Every package under ``src/`` other than the dataset and the eval scorer is the system under test.
It may read the released corpus, never world data, the answer key or the scorer: a pipeline or
prompt built from them would score well and prove nothing. Until the first system package exists
this test passes vacuously; it starts guarding as soon as one is added.

The other way round, the scorer never reads Protocols, decisions or the database (spec #247).
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

from traceq.ai.port import Prompt
from traceq.protocols.prompts import PROMPTS as PROTOCOLS
from traceq.review.draft import DRAFT_PROMPT
from traceq.review.prompts import PROMPTS as REVIEW
from traceq.traceability.prompts import PROMPTS as TRACEABILITY
from traceq_dataset.answer_key import load_key
from traceq_dataset.review_package import load_package, load_package_key
from traceq_eval.citations import norm

SRC = Path(__file__).parents[1] / "src"
HARNESS = {"traceq_dataset", "traceq_eval"}
FORBIDDEN_IMPORTS = HARNESS
PROMPTS = (*TRACEABILITY, *REVIEW, *PROTOCOLS, DRAFT_PROMPT)
FORBIDDEN_TEXT = (
    "answer_key",
    "world/",
    "world\\",
    "tp201.yaml",
    "tp202.yaml",
    "pw001.yaml",  # held-out PW-001 (spec #195)
    "baselines/",
    # Review Package TP-201-OQ-draft (spec #196): its world data, its key's files and its
    # baseline. The system reads only its release folder (the draft and manifest.json).
    "tp201-oq-draft.yaml",
    "defects.yaml",
    "clean_traps.yaml",
    "injection_probes.yaml",
    "test_steps.yaml",
    "TP-201-OQ-draft.json",
)


def system_files() -> list[Path]:
    return sorted(
        f
        for pkg in SRC.iterdir()
        if pkg.is_dir() and pkg.name not in HARNESS and not pkg.name.startswith((".", "_"))
        for f in pkg.rglob("*")
        if f.is_file() and f.suffix in {".py", ".md", ".txt", ".yaml", ".yml", ".json", ".jinja"}
    )


def leaks(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    found = [f"mentions {t!r}" for t in FORBIDDEN_TEXT if t in text]
    if path.suffix == ".py":
        for node in ast.walk(ast.parse(text)):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            found += [f"imports {n}" for n in names if n.split(".")[0] in FORBIDDEN_IMPORTS]
    return found


@pytest.mark.parametrize("path", system_files(), ids=lambda p: p.relative_to(SRC).as_posix())
def test_system_does_not_see_the_answer_key(path: Path) -> None:
    assert leaks(path) == []


def test_guard_catches_a_leak(tmp_path: Path) -> None:
    bad = tmp_path / "prompt.py"
    bad.write_text("from traceq_dataset.answer_key import derive\nP = 'answer_key/TP-201'\n")
    assert leaks(bad) == ["mentions 'answer_key'", "imports traceq_dataset.answer_key"]


def test_guard_catches_a_review_package_leak(tmp_path: Path) -> None:
    bad = tmp_path / "draft.py"
    bad.write_text(
        "W = 'tp201-oq-draft.yaml'\nT = 'clean_traps.yaml'\nB = 'TP-201-OQ-draft.json'\n"
    )
    assert leaks(bad) == [
        "mentions 'tp201-oq-draft.yaml'",
        "mentions 'clean_traps.yaml'",
        "mentions 'TP-201-OQ-draft.json'",
    ]


def copied(prompt: str, equipment: str) -> list[str]:
    """What a prompt takes from a dataset Equipment: its tag, or one of its URS requirements
    as printed."""
    key = load_key(SRC.parent / "answer_key" / equipment)
    texts = [norm(r["text"]) for r in key["requirements.yaml"]]
    text = norm(prompt)
    return [t for t in [equipment, *texts] if t in text]


@pytest.mark.parametrize("prompt", PROMPTS, ids=lambda p: p.name)
@pytest.mark.parametrize("equipment", ["TP-201", "TP-202", "PW-001"])
def test_prompt_examples_are_invented(equipment: str, prompt: Prompt) -> None:
    """Examples are invented, never taken from the development or the held-out Equipment.
    The message gives counts only: the copied text may be held out."""
    found = copied(prompt.system, equipment)
    assert not found, f"{equipment} {prompt.name}: {len(found)} copied"


NO_LLM = SRC / "traceq" / "runs" / "no_llm.py"


@pytest.mark.parametrize("equipment", ["TP-201", "TP-202", "PW-001"])
def test_no_llm_rules_are_invented(equipment: str) -> None:
    """The No-LLM Baseline's rules hold no Equipment tag, requirement id or requirement text
    of the development or the held-out Equipment (#193)."""
    source = NO_LLM.read_text(encoding="utf-8")
    ids = [r["id"] for r in load_key(SRC.parent / "answer_key" / equipment)["requirements.yaml"]]
    assert copied(source, equipment) == []
    assert [i for i in ids if i in source] == []
    assert equipment.replace("-", "") not in source


def test_copy_guard_catches_a_requirement() -> None:
    first = load_key(SRC.parent / "answer_key" / "TP-202")["requirements.yaml"][0]["text"]
    assert copied(f"Example: {first}", "TP-202") == [norm(first)]


def test_draft_prompt_takes_nothing_from_the_tp201_draft() -> None:
    """The draft prompt's examples come neither from TP-201 nor from its Protocol Draft: no
    Test Step id, AC or Injection Probe text of the package is in it (spec #196)."""
    root = SRC.parent
    package = load_package(root / "world" / "tp201-oq-draft.yaml")
    key = load_package_key(root / "answer_key" / package.id)
    texts = [
        *(s.id for s in package.steps),
        *(t for s in package.steps for t in (s.acceptance.text, s.title)),
        *(a.text for s in package.steps for a in (s.deviates, s.trap) if a is not None),
        package.injection_probes.remarks,
        *(p["location"]["text"] for p in key["injection_probes.yaml"]),
        package.document.id,
    ]
    prompt = norm(DRAFT_PROMPT.system)
    assert [t for t in texts if norm(t) in prompt] == []


# --- The other way: eval runs never read Protocols, Executions or decisions (#247, #271) ---
SCORER_NEVER_LOADS = ("traceq.execution", "traceq.assembly", "traceq.proposals", "traceq.db")
_IMPORT_THE_SCORER = """
import importlib, json, pkgutil, sys
import traceq_eval
for m in pkgutil.walk_packages(traceq_eval.__path__, "traceq_eval."):
    importlib.import_module(m.name)
print(json.dumps(sorted(sys.modules)))
"""


def loaded_by(program: str) -> list[str]:
    """The modules a fresh interpreter has loaded after running ``program``."""
    done = subprocess.run(
        [sys.executable, "-c", program], capture_output=True, text=True, check=True
    )
    return json.loads(done.stdout)


def never_loaded(modules: list[str]) -> list[str]:
    """The modules of ``modules`` that the scorer must never load."""
    return [m for m in modules if any(m == p or m.startswith(f"{p}.") for p in SCORER_NEVER_LOADS)]


def test_the_scorer_never_loads_protocols_decisions_or_the_database() -> None:
    """Importing the scorer package and every module of it (it imports ``traceq.runs.run``)
    loads neither the Protocol package, nor Proposals and their decisions, nor the database."""
    modules = loaded_by(_IMPORT_THE_SCORER)
    assert "traceq.runs.run" in modules
    assert never_loaded(modules) == []


def test_the_scorer_guard_catches_a_load() -> None:
    assert never_loaded(["traceq.proposals.decisions", "traceq.db", "traceq.dbx", "traceq"]) == [
        "traceq.proposals.decisions",
        "traceq.db",
    ]
