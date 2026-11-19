"""``docker/corpus.Dockerfile``: the release recipe renders every Equipment that has an answer key
(#239). A Review Package (world data with an ``id`` and no ``tag``) is rendered by its own module
and is not part of the corpus."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parents[1]
RECIPE = ROOT / "docker" / "corpus.Dockerfile"


def _cmd_args() -> list[str]:
    line = next(
        ln for ln in RECIPE.read_text(encoding="utf-8").splitlines() if ln.startswith("CMD ")
    )
    args = json.loads(line.removeprefix("CMD "))
    assert isinstance(args, list)
    return [str(a) for a in args]


def _keyed_equipment_worlds() -> list[str]:
    worlds: list[str] = []
    for path in sorted((ROOT / "world").glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        tag = data.get("tag") if isinstance(data, dict) else None
        if isinstance(tag, str) and (ROOT / "answer_key" / tag).is_dir():
            worlds.append(f"world/{path.name}")
    return worlds


def test_recipe_renders_every_equipment_with_an_answer_key() -> None:
    args = _cmd_args()
    worlds = _keyed_equipment_worlds()
    assert len(worlds) >= 2
    missing = sum(w not in args for w in worlds)
    # Report a count only: the names of held-out Equipment stay out of the test output.
    if missing:
        pytest.fail(f"{missing} keyed world file(s) not rendered by the recipe", pytrace=False)


def test_recipe_renders_into_out() -> None:
    args = _cmd_args()
    assert args[args.index("--out") + 1] == "/out"
    assert all(re.fullmatch(r"world/[a-z0-9-]+\.yaml", a) for a in args if a.startswith("world/"))
