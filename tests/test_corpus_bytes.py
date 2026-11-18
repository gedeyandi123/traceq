"""Byte guard: TP-201 and TP-202 render exactly as the corpus-0.1.1 release (ticket #199).

Optional dataset fields must leave both corpora unchanged with their defaults, so every
published file is compared with ``recordings/corpus-0.1.1/manifest.json`` by sha256 and size.

The XLSX differs by platform in one field only: the host-OS byte ("version made by") of each
zip central-directory entry, which Python's ``zipfile`` sets from the platform it runs on
(0 on Windows, 3 on Unix, where the release was built). When its bytes differ, that byte is
set to Unix and the file is compared again, still byte for byte, so every cell value, style
and zip entry is covered. Failure messages print paths and hashes only, never document text.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest

from traceq_dataset.corpus import build_corpus
from traceq_dataset.world import load

ROOT = Path(__file__).parents[1]
MANIFEST = ROOT / "recordings" / "corpus-0.1.1" / "manifest.json"
CENTRAL_ENTRY = b"PK\x01\x02"
UNIX = 3


def _released() -> dict[str, dict[str, Any]]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {d["path"]: d for d in manifest["documents"]}


def unix_zip(data: bytes) -> bytes:
    """A zip with the host-OS byte of every central-directory entry set to Unix."""
    out = bytearray(data)
    pos = out.find(CENTRAL_ENTRY)
    while pos >= 0:
        out[pos + 5] = UNIX
        pos = out.find(CENTRAL_ENTRY, pos + len(CENTRAL_ENTRY))
    return bytes(out)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_unix_zip_sets_only_the_host_byte() -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        info = zipfile.ZipInfo("a.xml", date_time=(2026, 1, 1, 0, 0, 0))
        info.create_system = 0
        z.writestr(info, b"<a/>")
    data = buf.getvalue()
    patched = unix_zip(data)
    assert len(patched) == len(data)
    assert sum(a != b for a, b in zip(data, patched, strict=True)) == 1
    with zipfile.ZipFile(io.BytesIO(patched)) as z:
        assert [i.create_system for i in z.infolist()] == [UNIX]
        assert z.read("a.xml") == b"<a/>"


@pytest.mark.parametrize("world", ["tp201", "tp202"])
def test_corpus_matches_the_release(world: str) -> None:
    corpus = build_corpus(load(ROOT / "world" / f"{world}.yaml"))
    released = {p: d for p, d in _released().items() if d["equipment"] == corpus.eq.tag}
    problems: list[str] = []
    rendered: set[str] = set()
    for key, r in corpus.rendered.items():
        path = f"{corpus.eq.tag}/{corpus.filename(key)}"
        rendered.add(path)
        want = released.get(path)
        if want is None:
            problems.append(f"{path}: not in the release")
            continue
        data = corpus.published(key)
        if r.format == "xlsx" and _sha(data) != want["sha256"]:
            data = unix_zip(data)
        if (_sha(data), len(data)) != (want["sha256"], want["bytes"]):
            problems.append(
                f"{path}: sha256 {_sha(data)[:12]} ({len(data)} bytes), "
                f"release {want['sha256'][:12]} ({want['bytes']} bytes)"
            )
    problems += [f"{p}: released but not rendered" for p in sorted(set(released) - rendered)]
    assert problems == []
