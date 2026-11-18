"""``scripts/pack_release.py``: the corpus tarball is deterministic, 0.1.x layout (#171)."""

from __future__ import annotations

import gzip
import hashlib
import importlib.util
import io
import tarfile
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "pack_release.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("pack_release", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def src(tmp_path: Path) -> Path:
    root = tmp_path / "src" / "t0-2026-06-01"
    (root / "alpha").mkdir(parents=True)
    (root / "Zed").mkdir()
    (root / "a.txt").write_bytes(b"alpha")
    (root / "alpha" / "z.pdf").write_bytes(b"zed")
    (root / "Zed" / "y.pdf").write_bytes(b"why")
    (root / "manifest.json").write_bytes(b"{}")
    return tmp_path / "src"


def test_layout_and_metadata(src: Path, tmp_path: Path) -> None:
    out = tmp_path / "corpus-9.9.9.tar.gz"
    digest = _load().pack(src, out)
    raw = out.read_bytes()

    assert raw[:3] == b"\x1f\x8b\x08"
    assert raw[3] == 0  # no flags, so no file name
    assert raw[4:8] == b"\x00\x00\x00\x00"  # gzip mtime 0
    assert raw[9] == 3  # OS byte: unix

    stream = gzip.decompress(raw)
    assert stream[257:265] == b"ustar  \x00"  # GNU magic and version
    with tarfile.open(fileobj=io.BytesIO(stream)) as tar:
        members = tar.getmembers()
    assert [m.name for m in members] == [
        "t0-2026-06-01",
        "t0-2026-06-01/Zed",  # POSIX order: upper case before lower case
        "t0-2026-06-01/Zed/y.pdf",
        "t0-2026-06-01/a.txt",
        "t0-2026-06-01/alpha",
        "t0-2026-06-01/alpha/z.pdf",
        "t0-2026-06-01/manifest.json",
    ]
    for m in members:
        assert (m.mtime, m.uid, m.gid, m.uname, m.gname) == (1780272000, 0, 0, "", "")
        assert m.mode == (0o755 if m.isdir() else 0o644)

    line = out.with_name(out.name + ".sha256").read_bytes()
    assert line == f"{hashlib.sha256(raw).hexdigest()}  {out.name}\n".encode()
    assert digest == hashlib.sha256(raw).hexdigest()


def test_packing_twice_gives_identical_bytes(src: Path, tmp_path: Path) -> None:
    pack = _load().pack
    pack(src, tmp_path / "one.tar.gz")
    pack(src, tmp_path / "two.tar.gz")
    assert (tmp_path / "one.tar.gz").read_bytes() == (tmp_path / "two.tar.gz").read_bytes()


def test_packs_a_review_package_folder(tmp_path: Path) -> None:
    root = tmp_path / "src" / "TP-201-OQ-draft"
    root.mkdir(parents=True)
    (root / "OQ-TP201_rev0.pdf").write_bytes(b"draft")
    (root / "manifest.json").write_bytes(b"{}")
    out = tmp_path / "TP-201-OQ-draft-0.1.0.tar.gz"
    _load().pack(tmp_path / "src", out, root_name="TP-201-OQ-draft")
    with tarfile.open(fileobj=io.BytesIO(gzip.decompress(out.read_bytes()))) as tar:
        names = tar.getnames()
    assert names == [
        "TP-201-OQ-draft",
        "TP-201-OQ-draft/OQ-TP201_rev0.pdf",
        "TP-201-OQ-draft/manifest.json",
    ]
