"""Deterministic ``corpus-<version>.tar.gz`` of ``t0-2026-06-01/`` (the corpus release asset).

    uv run python scripts/pack_release.py SRC OUT.tar.gz

``SRC`` is the folder that contains ``t0-2026-06-01/`` (the build output). Layout of the 0.1.x
assets: GNU tar format, members sorted by POSIX path (not the Windows case-insensitive order),
mtime 2026-06-01, uid/gid 0 with empty names, modes 755 (folders) and 644 (files), gzip
without a file name or timestamp and OS byte 3 (unix, as gzip(1)). It also writes
``OUT.tar.gz.sha256`` in ``sha256sum`` format and prints the hash.

The tar stream is reproducible across machines; the gzip bytes depend on the deflate
implementation, so the tarball hash is not reproducible across tools (the contents are).
"""

from __future__ import annotations

import gzip
import hashlib
import io
import sys
import tarfile
from pathlib import Path

ROOT_NAME = "t0-2026-06-01"
MTIME = 1780272000  # 2026-06-01T00:00:00Z


def pack(src: Path, out: Path) -> str:
    """Write the tarball and its ``.sha256`` file; return the hex digest."""
    root = src / ROOT_NAME
    paths = [root, *sorted(root.rglob("*"), key=lambda p: p.relative_to(src).as_posix())]
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.GNU_FORMAT) as tar:
        for p in paths:
            info = tar.gettarinfo(str(p), arcname=p.relative_to(src).as_posix())
            info.mtime, info.uid, info.gid, info.uname, info.gname = MTIME, 0, 0, "", ""
            if p.is_dir():
                info.mode = 0o755
                tar.addfile(info)
            else:
                info.mode = 0o644
                with p.open("rb") as f:
                    tar.addfile(info, f)
    raw = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
        gz.write(buf.getvalue())
    data = bytearray(raw.getvalue())
    data[9] = 3
    out.write_bytes(bytes(data))
    digest = hashlib.sha256(data).hexdigest()
    with out.with_name(out.name + ".sha256").open("w", encoding="utf-8", newline="\n") as f:
        f.write(f"{digest}  {out.name}\n")
    return digest


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    print(pack(Path(argv[0]), Path(argv[1])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
