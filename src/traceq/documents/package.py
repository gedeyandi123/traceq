"""A released Review Package directory (spec #196): ``manifest.json`` plus its Protocol Draft.

The package refers to one corpus release by version and by the SHA-256 of that release's
``manifest.json``, and names its Equipment. A run takes the package only beside that corpus
and that Equipment.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DATASET = "traceq-review-package"


@dataclass(frozen=True)
class ReviewPackage:
    root: Path
    package: str
    version: str
    equipment: str
    corpus_release: str
    corpus_version: str
    corpus_manifest_sha256: str

    @classmethod
    def load(cls, root: Path) -> ReviewPackage:
        """Read ``root/manifest.json``; ``ValueError`` when it is not a Review Package."""
        manifest: dict[str, Any] = json.loads((root / "manifest.json").read_text("utf-8"))
        if manifest.get("dataset") != DATASET:
            raise ValueError(f"{root}: not a Review Package (dataset {manifest.get('dataset')!r})")
        corpus: dict[str, Any] = manifest["corpus"]
        return cls(
            root=root,
            package=str(manifest["package"]),
            version=str(manifest["version"]),
            equipment=str(manifest["equipment"]),
            corpus_release=str(corpus["release"]),
            corpus_version=str(corpus["version"]),
            corpus_manifest_sha256=str(corpus["manifest_sha256"]),
        )

    def check_fits(self, corpus_root: Path, equipment: str) -> None:
        """``ValueError`` unless ``corpus_root`` is the release the package refers to and
        ``equipment`` is the package's Equipment."""
        if equipment != self.equipment:
            raise ValueError(
                f"Review Package {self.package} is for {self.equipment}, not {equipment}"
            )
        got = hashlib.sha256((corpus_root / "manifest.json").read_bytes()).hexdigest()
        if got != self.corpus_manifest_sha256:
            raise ValueError(
                f"Review Package {self.package} refers to corpus release {self.corpus_release}"
                f" (manifest SHA-256 {self.corpus_manifest_sha256[:12]}…), not to"
                f" {corpus_root} ({got[:12]}…)"
            )
