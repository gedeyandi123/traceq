"""What the worker runs for one uploaded draft: a Review Package run over that one revision.

The uploaded PDF becomes a one-document Review Package beside the corpus (``traceq.documents.
package``), and ``traceq.runs.run`` reads it exactly as ``traceq run --review-package`` does:
the Equipment stages replay from the recordings, never sent; the draft is read with the
recording its bytes already have, so a re-upload of the same bytes replays and costs nothing
live. Only bytes with no recording go to Mode Cloud, and only when a live adapter is
configured and the job holds a reservation (``max_usd`` is that reservation).
"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from traceq.ai import LLM
from traceq.documents.package import DATASET
from traceq.runs.run import run
from traceq.uploads.store import Job


@dataclass(frozen=True)
class UploadSettings:
    """Where uploads are accepted and how they are run.

    ``equipment``: the one Equipment uploads are accepted for (the scope of the routes).
    ``store``: where uploaded files (named by their hash) and each job's package are kept.
    ``corpus``, ``recordings``, ``package_recordings``, ``model``: as for ``traceq run``.
    ``budget_usd``: the ceiling of live spend over all uploads; 0 means replay only.
    ``live``: the adapter for bytes with no recording, used only when the ceiling allows.
    ``package_version``: the Review Package version, which selects the draft prompt.
    """

    equipment: str
    store: Path
    corpus: Path
    recordings: Path
    package_recordings: Path
    model: str
    budget_usd: float = 0.0
    live: Callable[[], LLM] | None = None
    package_version: str = "0.2.0"
    language: str = "id"
    max_bytes: int = 10 * 1024 * 1024
    max_pages: int = 40
    estimate_per_page_usd: float = 0.002
    """What a page with no recording may cost live, as a ceiling for the reservation (one
    recorded draft run cost about USD 0.0018 for the whole draft)."""

    @property
    def blobs(self) -> Path:
        return self.store / "files"


@dataclass(frozen=True)
class RunResult:
    run_id: str
    live_cost_usd: float


Runner = Callable[[Job, Path], RunResult]
"""``(job, path of the stored PDF)`` to the run it wrote; it raises when the run fails."""


def draft_doc_id(equipment: str) -> str:
    """The id every revision of an Equipment's uploaded draft carries, so that a later upload
    is a revision of the same document."""
    return "OQ-" + equipment.replace("-", "")


def write_package(settings: UploadSettings, job: Job, pdf: Path, dest: Path) -> Path:
    """A Review Package holding the one uploaded revision, at ``dest``."""
    corpus: dict[str, Any] = json.loads((settings.corpus / "manifest.json").read_text("utf-8"))
    version = str(corpus["version"])
    package = f"UPLOAD-{settings.equipment}"
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(pdf, dest / "draft.pdf")
    manifest = {
        "dataset": DATASET,
        "package": package,
        "version": settings.package_version,
        "label": "uploaded in the browser; dev only, synthetic data only",
        "equipment": settings.equipment,
        "corpus": {
            "release": f"corpus-v{version}",
            "version": version,
            "manifest_sha256": hashlib.sha256(
                (settings.corpus / "manifest.json").read_bytes()
            ).hexdigest(),
        },
        "documents": [
            {
                "path": "draft.pdf",
                "doc_id": draft_doc_id(settings.equipment),
                "rev": job.rev,
                "type": "oq_protocol",
                "status": "Draft",
                "language": settings.language,
                "format": "born_digital",
                "pages": job.pages,
                "bytes": job.size_bytes,
                "sha256": job.sha256,
            }
        ],
    }
    (dest / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return dest


def package_runner(settings: UploadSettings, runs: Path) -> Runner:
    """The production runner: a Review Package run over the job's revision, into ``runs``."""

    def go(job: Job, pdf: Path) -> RunResult:
        package = write_package(settings, job, pdf, settings.store / "packages" / str(job.id))
        live = (
            settings.live()
            if settings.live is not None and job.reserved_usd > 0 and settings.budget_usd > 0
            else None
        )
        out = run(
            settings.corpus,
            runs,
            settings.recordings,
            settings.model,
            equipment=settings.equipment,
            live=live,
            max_usd=float(job.reserved_usd),
            review_package=package,
            package_recordings=settings.package_recordings,
            draft_rev=job.rev,
        )
        return RunResult(str(out.metadata["run_id"]), float(out.metadata["live_cost_usd"]))

    return go
