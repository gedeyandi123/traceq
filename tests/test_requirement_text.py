"""Shown requirement text: the id and the Kritis cell are dropped from output only (#145)."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from traceq.ai import Request, Response
from traceq.documents import Corpus
from traceq.documents.cache import IngestCache, Ingested
from traceq.documents.corpus import CorpusDocument
from traceq.documents.pages import Page
from traceq.documents.pdf import PDF_VERSION
from traceq.traceability import Citation, Requirement, Traceability, trace
from traceq.traceability.requirement_text import clean_requirement_text, has_kritis_column

ID = "URS-TP201-024"


@pytest.mark.parametrize("cell", ["Ya", "Tidak", "Yes", "No"])
def test_id_and_kritis_cell_dropped_with_header(cell: str) -> None:
    got = clean_requirement_text(f"{ID} {cell} Resep produk dapat di-backup.", ID, True)
    assert got == "Resep produk dapat di-backup."


def test_pipe_separated_row() -> None:
    assert clean_requirement_text(f"{ID} | Tidak | Resep produk.", ID, True) == "Resep produk."


@pytest.mark.parametrize("first", ["Tidak", "No"])
def test_meaning_kept_without_kritis_column(first: str) -> None:
    got = clean_requirement_text(f"{ID} {first} boleh ada kebocoran", ID, False)
    assert got == f"{first} boleh ada kebocoran"


def test_cell_needs_token_boundary() -> None:
    assert clean_requirement_text(f"{ID} Yamaha pump", ID, True) == "Yamaha pump"
    assert clean_requirement_text(f"{ID} Nomor seri", ID, True) == "Nomor seri"


def test_idempotent() -> None:
    once = clean_requirement_text(f"{ID} Tidak Resep produk.", ID, True)
    assert clean_requirement_text(once, ID, True) == once


def test_without_printed_id_unchanged() -> None:
    assert clean_requirement_text("Tidak Resep produk.", None, True) == "Tidak Resep produk."
    assert clean_requirement_text("Tidak Resep produk.", "", True) == "Tidak Resep produk."


def test_text_not_starting_with_its_id_unchanged() -> None:
    text = f"Mesin memiliki 36 stasiun punch. {ID}"
    assert clean_requirement_text(text, ID, True) == text
    assert clean_requirement_text("Tidak Resep produk.", ID, True) == "Tidak Resep produk."


def test_id_prefix_of_longer_id_is_not_dropped() -> None:
    assert clean_requirement_text("URS-TP201-0245 Ya x", ID, True) == "URS-TP201-0245 Ya x"


def test_has_kritis_column() -> None:
    assert has_kritis_column(["Judul\nNo. | Kritis | Persyaratan\n1 | Ya | x"])
    assert has_kritis_column(["a", "No.  KRITIS   persyaratan"])
    assert not has_kritis_column(["Persyaratan\nURS-1 Tidak boleh bocor"])
    assert not has_kritis_column(["Kritis\n", "Persyaratan\n"])  # different lines
    assert not has_kritis_column(["Nonkritis persyaratan"])  # whole words only


def test_requirement_default_shown_and_positional_constructor() -> None:
    r = Requirement("R1", "text", Citation("U", 1, 1, "q"), True)
    assert r.shown is None


def test_matrix_shows_clean_text_and_keeps_quote() -> None:
    from traceq.runs.matrix import matrix

    row = f"{ID} Tidak Resep produk dapat di-backup."
    c = Citation("URS-TP201", 1, 2, row)
    r = Requirement(ID, row, c, True, shown="Resep produk dapat di-backup.")
    m = matrix(Traceability(requirements=[r]))
    assert m.requirements[0].text == "Resep produk dapat di-backup."
    assert m.requirements[0].source.quote == row
    plain = Requirement("R2", "plain", c, False)
    assert matrix(Traceability(requirements=[plain])).requirements[0].text == "plain"


ROW = "URS-X-002 Tidak Resep produk dapat di-backup."
HEADER = "No. | Kritis | Persyaratan"


class _Recording:
    model = "scripted"

    def __init__(self) -> None:
        self.users: dict[str, list[str]] = {}

    def complete(self, requests: Sequence[Request]) -> list[Response]:
        out: list[Response] = []
        for r in requests:
            self.users.setdefault(r.prompt.name, []).append(r.user)
            answer: dict[str, Any]
            if r.prompt.name == "segment":
                answer = {"requirements": [{"id": "URS-X-002", "text": ROW, "quote": ROW}]}
            elif r.prompt.name == "extract":
                blank = dict.fromkeys(("min", "max", "number", "unit", "text"))
                answer = {"kind": "none", **blank, "allowed": [], "quote": ""}
            else:
                answer = {
                    "steps": [],
                    "rows": [],
                    "site_only": False,
                    "transport_sensitive": False,
                    "area": None,
                }
            out.append(Response(json.dumps(answer), "scripted", 1, 1))
        return out


def _corpus(tmp_path: Path, page: str) -> Corpus:
    doc = CorpusDocument("URS-X", 0, "urs", "born_digital", "id", tmp_path / "u.pdf", "abc")
    cache = IngestCache(tmp_path / "ingest")
    cache.put(Ingested("abc", PDF_VERSION, "fake", (Page(1, page),), (0.0, 0.0), 0.0, None))
    return Corpus(tmp_path, "X", (doc,), cache=cache)


def test_trace_shows_clean_text_but_prompts_keep_the_original(tmp_path: Path) -> None:
    llm = _Recording()
    t = trace(_corpus(tmp_path, f"{HEADER}\n{ROW}"), llm)
    assert t.requirements[0].text == ROW
    assert t.requirements[0].shown == "Resep produk dapat di-backup."
    assert llm.users["extract"][0].startswith(
        json.dumps({"id": "URS-X-002", "requirement": ROW}, ensure_ascii=False)
    )
    assert any(ROW in u for u in llm.users["link"])


def test_trace_without_kritis_header_keeps_the_cell(tmp_path: Path) -> None:
    t = trace(_corpus(tmp_path, ROW), _Recording())
    assert t.requirements[0].shown == "Tidak Resep produk dapat di-backup."
