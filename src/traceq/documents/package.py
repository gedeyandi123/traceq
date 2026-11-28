"""A released Review Package directory (spec #196): ``manifest.json`` plus its Protocol Draft.

The package refers to one corpus release by version and by the SHA-256 of that release's
``manifest.json``, and names its Equipment. A run takes the package only beside that corpus
and that Equipment.

A document's ``path`` in the manifest starts with the package folder's name
(``<package>/<file>``, as the release archive holds it), so it is read from the package
directory without that first part; a path that does not start with it is read from the
package directory as it stands.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from traceq.documents.corpus import CorpusDocument

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
    documents: tuple[CorpusDocument, ...] = ()

    @classmethod
    def load(cls, root: Path) -> ReviewPackage:
        """Read ``root/manifest.json``; ``ValueError`` when it is not a Review Package."""
        manifest: dict[str, Any] = json.loads((root / "manifest.json").read_text("utf-8"))
        if manifest.get("dataset") != DATASET:
            raise ValueError(f"{root}: not a Review Package (dataset {manifest.get('dataset')!r})")
        corpus: dict[str, Any] = manifest["corpus"]
        package = str(manifest["package"])
        entries: list[dict[str, Any]] = manifest.get("documents", [])
        return cls(
            root=root,
            package=package,
            version=str(manifest["version"]),
            equipment=str(manifest["equipment"]),
            corpus_release=str(corpus["release"]),
            corpus_version=str(corpus["version"]),
            corpus_manifest_sha256=str(corpus["manifest_sha256"]),
            documents=tuple(
                CorpusDocument(
                    doc_id=str(d["doc_id"]),
                    rev=int(d["rev"]),
                    type=str(d["type"]),
                    format=str(d["format"]),
                    language=str(d.get("language") or "en"),
                    path=_path(root, package, str(d["path"])),
                    sha256=str(d["sha256"]),
                )
                for d in entries
            ),
        )

    def draft(self, rev: int | None = None) -> CorpusDocument:
        """The Protocol Draft of revision ``rev``, or of the latest revision when none is
        chosen. A package holds several revisions of its draft; a run reads exactly one
        document of the chosen revision, and ``ValueError`` says otherwise."""
        if not self.documents:
            raise ValueError(f"Review Package {self.package} holds no Protocol Draft")
        chosen = max(d.rev for d in self.documents) if rev is None else rev
        of_rev = [d for d in self.documents if d.rev == chosen]
        if not of_rev:
            held = ", ".join(str(r) for r in sorted({d.rev for d in self.documents}))
            raise ValueError(
                f"Review Package {self.package} has no draft revision {chosen} (it holds {held})"
            )
        if len(of_rev) != 1:
            raise ValueError(
                f"Review Package {self.package} holds {len(of_rev)} documents of revision"
                f" {chosen}; exactly one Protocol Draft is expected"
            )
        return of_rev[0]

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


def _path(root: Path, package: str, path: str) -> Path:
    parts = Path(path).parts
    return root.joinpath(*parts[1:]) if len(parts) > 1 and parts[0] == package else root / path
