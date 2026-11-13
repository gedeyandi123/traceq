"""The TraceQ system must not see what it is scored against (design section 6, "Answer key").

Every package under ``src/`` other than the dataset and the eval scorer is the system under test.
It may read the released corpus, never world data, the answer key or the scorer: a pipeline or
prompt built from them would score well and prove nothing. Until the first system package exists
this test passes vacuously; it starts guarding as soon as one is added.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).parents[1] / "src"
HARNESS = {"traceq_dataset", "traceq_eval"}
FORBIDDEN_IMPORTS = HARNESS
FORBIDDEN_TEXT = ("answer_key", "world/", "world\\", "tp201.yaml", "tp202.yaml", "baselines/")


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
