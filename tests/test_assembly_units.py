"""Units of the assembled Protocol that need no database (spec #247; ticket #264)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from traceq.assembly import missed
from traceq.runs import api as runs_api
from traceq.runs.completeness import COMPLETENESS_FILE


def test_the_completeness_check_is_read_through_the_served_file_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / COMPLETENESS_FILE).write_text(json.dumps({"urs": []}), encoding="utf-8")
    got = missed.check_of(tmp_path)
    assert got is not None
    assert got.urs == ()
    monkeypatch.setattr(runs_api, "SERVED", ())
    with pytest.raises(ValueError, match="not a file the API serves"):
        missed.check_of(tmp_path)


def test_a_run_without_a_completeness_check_has_none(tmp_path: Path) -> None:
    assert missed.check_of(tmp_path) is None
    assert missed.check_of(None) is None
