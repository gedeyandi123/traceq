"""The web's copy of the decision vocabulary equals the API's (spec #105).

The API is the authority: it checks the role and the Coverage class on every call. The web
keeps a display-only copy in one module; this test keeps the two from drifting.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import get_args

from traceq.identity import APPROVING_ROLE, DECIDING_ROLE, EXECUTING_ROLE
from traceq.traceability.coverage import CoverageClass

VOCABULARY = Path(__file__).parents[1] / "web" / "src" / "decisions" / "vocabulary.ts"


def _source() -> str:
    return VOCABULARY.read_text(encoding="utf-8")


def test_the_web_names_the_deciding_role_as_the_api_does() -> None:
    found = re.findall(r'export const DECIDING_ROLE = "([^"]+)";', _source())
    assert found == [DECIDING_ROLE]


def test_the_web_names_the_approving_role_as_the_api_does() -> None:
    found = re.findall(r'export const APPROVING_ROLE = "([^"]+)";', _source())
    assert found == [APPROVING_ROLE]


def test_the_web_names_the_executing_role_as_the_api_does() -> None:
    found = re.findall(r'export const EXECUTING_ROLE = "([^"]+)";', _source())
    assert found == [EXECUTING_ROLE]


def test_the_web_lists_the_coverage_classes_as_the_api_does() -> None:
    block = re.search(
        r"COVERAGE_CLASS_ORDER: Record<CoverageClass, number> = \{(.*?)\};", _source(), re.S
    )
    assert block is not None
    entries = re.findall(r"^\s*(\w+): (\d+),$", block.group(1), re.M)
    in_order = [name for name, _ in sorted(entries, key=lambda e: int(e[1]))]
    assert in_order == list(get_args(CoverageClass))
