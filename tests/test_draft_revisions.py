"""Several draft revisions in one Review Package, a versioned answer-key location and the
draft stage's own version (spec #375, ticket S0b).

The Equipment stages keep their recording keys (PIPELINE_VERSION is not bumped); the draft
stage is keyed on ``DRAFT_STAGE_VERSION``, which starts equal to the 0.1.0 value so 0.1.0's
recordings replay; 0.1.0's answer key keeps its bytes.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from traceq.ai import MissingRecording, Recorder, Request
from traceq.documents import ReviewPackage
from traceq.review.draft import DRAFT_PROMPT, DRAFT_STAGE_VERSION
from traceq.runs import run as run_module
from traceq.runs.run import run
from traceq.traceability import PIPELINE_VERSION, PROMPTS
from traceq_dataset.review_package import KEY_FILES, package_key_dir
from traceq_eval.report import key_sha256

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "recordings" / "corpus-0.1.1"
R10 = ROOT / "recordings" / "haiku-r10"
PACKAGE = ROOT / "recordings" / "TP-201-OQ-draft-0.1.0"
PACKAGE_RUN = ROOT / "recordings" / "haiku-oq-draft-r3"
MODEL = "claude-haiku-5-5"

EQUIPMENT_KEY = "7f9f84d1c45f3ff710aad24e0498116cf4e838075f2c1067c522e39f356c0785"
DRAFT_KEY = "746c7067b63d191b5f6a434ccef56e11def0b40553a92667389f891b3c0a21af"
"""Recording keys of a fixed request, computed before this ticket: the first of the first
Equipment prompt, the second of the draft prompt, both under pipeline 0.3.0."""
KEY_0_1_0 = "163c9675271ae3b23f7fdffc1235eb18a32904da584863cc58ea46a6d9310bd8"
"""SHA-256 over 0.1.0's answer-key files, as ``baselines/TP-201-OQ-draft-0.1.0.json`` records it."""


def _recorder(version: str) -> Recorder:
    return Recorder(Path("unused"), MODEL, version)


def test_equipment_stage_recording_keys_are_byte_identical() -> None:
    request = Request(PROMPTS[0], "user text", "a" * 64)
    assert PIPELINE_VERSION == "0.3.0"
    assert _recorder(PIPELINE_VERSION).key(request) == EQUIPMENT_KEY


def test_the_draft_stage_version_starts_equal_to_the_0_1_0_pipeline_version() -> None:
    request = Request(DRAFT_PROMPT, "user text", "a" * 64)
    assert DRAFT_STAGE_VERSION == "0.3.0"
    assert _recorder(DRAFT_STAGE_VERSION).key(request) == DRAFT_KEY


def test_a_stage_recorder_shares_the_call_log_and_changes_only_the_version() -> None:
    base = _recorder("1.0.0")
    stage = base.stage("2.0.0")
    request = Request(DRAFT_PROMPT, "user text", "a" * 64)
    assert stage.key(request) == _recorder("2.0.0").key(request) != base.key(request)
    assert stage.calls is base.calls
    assert (stage.store, stage.reads, stage.live, stage.budget) == (
        base.store,
        base.reads,
        base.live,
        base.budget,
    )


def test_0_1_0_answer_key_keeps_its_bytes() -> None:
    directory = package_key_dir(ROOT / "answer_key", "TP-201-OQ-draft", "0.1.0")
    assert directory == ROOT / "answer_key" / "TP-201-OQ-draft"
    assert key_sha256(directory, KEY_FILES) == KEY_0_1_0
    baseline: dict[str, Any] = json.loads(
        (ROOT / "baselines" / "TP-201-OQ-draft-0.1.0.json").read_text(encoding="utf-8")
    )
    assert baseline["review_package"]["answer_key_sha256"] == KEY_0_1_0


def test_a_later_version_has_a_key_folder_of_its_own() -> None:
    key = Path("answer_key")
    assert package_key_dir(key, "TP-201-OQ-draft", "0.2.0") == key / "TP-201-OQ-draft-0.2.0"
    assert package_key_dir(key, "TP-201-OQ-draft", "0.2.0") != package_key_dir(
        key, "TP-201-OQ-draft", "0.1.0"
    )


# --- Several draft revisions --------------------------------------------------------------


def _manifest() -> dict[str, Any]:
    return json.loads((PACKAGE / "manifest.json").read_text("utf-8"))


def _two_revisions(tmp_path: Path) -> Path:
    """The package with a second revision of the draft: the same bytes, so its ingest replays;
    its calls need a store of their own (``_store_with_revision_1``)."""
    manifest = _manifest()
    first = manifest["documents"][0]
    second = {**first, "rev": 1, "path": "TP-201-OQ-draft/OQ-TP201_rev1.pdf"}
    manifest["documents"] = [second, first]  # not in revision order, on purpose
    folder = tmp_path / "package"
    folder.mkdir()
    (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return folder


def _store_with_revision_1(tmp_path: Path) -> Path:
    """The committed package recordings, plus the draft calls asked of revision 1: the page
    prompt names the revision, so the same bytes read as revision 1 are other calls."""
    store = tmp_path / "package-rec"
    shutil.copytree(PACKAGE_RUN, store)
    recorder = Recorder(store, MODEL, DRAFT_STAGE_VERSION)
    for path in sorted(PACKAGE_RUN.glob("*.json")):
        record: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        if record.get("prompt") != DRAFT_PROMPT.name:
            continue
        user = record["request"]["user"].replace("revision 0,", "revision 1,", 1)
        request = Request(DRAFT_PROMPT, user, record["doc_sha256"])
        record["key"] = recorder.key(request)
        record["request"]["user"] = user
        (store / f"{record['key']}.json").write_text(json.dumps(record), encoding="utf-8")
    return store


def _draft_revs(out: Any) -> set[int]:
    sub = json.loads((out.folder / "submission.json").read_text(encoding="utf-8"))
    return {c["rev"] for f in sub["findings"] for c in f["citations"] if c["doc"] == "OQ-TP201"}


def test_a_package_holds_several_revisions_of_the_draft(tmp_path: Path) -> None:
    package = ReviewPackage.load(_two_revisions(tmp_path))
    assert [d.rev for d in package.documents] == [1, 0]
    assert package.draft(0).rev == 0
    assert package.draft(1).rev == 1
    assert package.draft().rev == 1  # the latest, when none is chosen


@pytest.mark.parametrize("rev", [2, -1])
def test_choosing_a_revision_the_package_lacks_is_refused(tmp_path: Path, rev: int) -> None:
    package = ReviewPackage.load(_two_revisions(tmp_path))
    with pytest.raises(ValueError, match=f"no draft revision {rev}"):
        package.draft(rev)


def test_a_package_without_a_draft_is_refused(tmp_path: Path) -> None:
    manifest = _manifest()
    manifest["documents"] = []
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="no Protocol Draft"):
        ReviewPackage.load(tmp_path).draft()


def test_two_documents_of_one_revision_are_refused(tmp_path: Path) -> None:
    manifest = _manifest()
    manifest["documents"] = [manifest["documents"][0]] * 2
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="2 documents of revision 0; exactly one"):
        ReviewPackage.load(tmp_path).draft(0)


def _run(out: Path, package: Path, store: Path = PACKAGE_RUN, **kwargs: Any) -> Any:
    return run(
        MANIFEST,
        out,
        R10,
        MODEL,
        equipment="TP-201",
        review_package=package,
        package_recordings=store,
        **kwargs,
    )


def test_a_run_takes_the_chosen_revision(tmp_path: Path) -> None:
    folder, store = _two_revisions(tmp_path), _store_with_revision_1(tmp_path)
    first = _run(tmp_path / "a", folder, store, draft_rev=0)
    second = _run(tmp_path / "b", folder, store, draft_rev=1)
    latest = _run(tmp_path / "c", folder, store)
    assert first.metadata["calls"]["live"] == second.metadata["calls"]["live"] == 0
    assert _draft_revs(first) == {0}
    assert _draft_revs(second) == _draft_revs(latest) == {1}


def test_a_revision_nobody_recorded_is_not_read_from_another(tmp_path: Path) -> None:
    """The committed recordings hold revision 0 only: asking for revision 1 fails instead of
    answering from revision 0's calls."""
    with pytest.raises(MissingRecording, match="protocol_draft"):
        _run(tmp_path / "runs", _two_revisions(tmp_path), draft_rev=1)


def test_a_run_over_a_missing_revision_is_refused_before_it_writes(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no draft revision 3"):
        _run(tmp_path / "runs", _two_revisions(tmp_path), draft_rev=3)
    assert not (tmp_path / "runs").exists()


# --- The draft stage is keyed on its own version -------------------------------------------


def test_the_draft_read_is_keyed_on_the_draft_stage_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Another draft stage version finds no recording of the draft, while the Equipment
    stages (still on PIPELINE_VERSION) replay."""
    monkeypatch.setattr(run_module, "DRAFT_STAGE_VERSION", "9.9.9")
    with pytest.raises(MissingRecording, match="protocol_draft"):
        _run(tmp_path / "runs", PACKAGE)
    assert not (tmp_path / "runs").exists()
