"""Degrader: SAT-TP201 as a scan, with handwritten boxes that follow the skew."""

from __future__ import annotations

import io
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw
from pypdf import PdfReader

from traceq_dataset.degrade import LEVELS, Scanned, degrade, rotate_quad
from traceq_dataset.render import EVAL_T0, Box, Rendered, render_sat
from traceq_dataset.validate import scan_problems
from traceq_dataset.world import load

TP201 = Path(__file__).parents[1] / "world" / "tp201.yaml"


@pytest.fixture(scope="module")
def sat() -> Rendered:
    return render_sat(load(TP201), "SAT-TP201", EVAL_T0)


@pytest.fixture(scope="module")
def scan(sat: Rendered) -> Scanned:
    return degrade(sat, "medium")


def _iou(a: np.ndarray, b: np.ndarray) -> float:
    return (a & b).sum() / (a | b).sum()


def _polygon(size: tuple[int, int], corners) -> np.ndarray:
    mask = Image.new("1", size)
    ImageDraw.Draw(mask).polygon(list(corners), fill=1)
    return np.asarray(mask)


@pytest.mark.parametrize("angle", [-2.0, -0.5, 0.5, 2.0])
@pytest.mark.parametrize("box", [Box(40, 40, 120, 20), Box(420, 780, 140, 20)])
def test_quad_follows_pillow_rotation(angle: float, box: Box) -> None:
    """rotate_quad must match what Image.rotate does to the pixels (A4 at 72 dpi)."""
    size = (595, 842)
    flat = ((box.x, box.y), (box.x + box.w, box.y), (box.x + box.w, box.y + box.h))
    page = Image.fromarray(_polygon(size, (*flat, (box.x, box.y + box.h))))
    rotated = np.asarray(page.rotate(angle))
    right = _iou(rotated, _polygon(size, rotate_quad(box, angle, *size)))
    wrong_sign = _iou(rotated, _polygon(size, rotate_quad(box, -angle, *size)))
    assert right > 0.85
    assert right > wrong_sign + 0.1


def test_scan_is_valid(sat: Rendered, scan: Scanned) -> None:
    assert scan_problems(scan) == []
    assert {k for k, p in scan.placed.items() if p.quad} == {
        k for k, p in sat.placed.items() if p.handwritten
    }
    lo, hi = LEVELS["medium"].skew
    assert all(lo <= abs(a) <= hi for a in scan.skew)


def test_scan_has_no_text_layer(scan: Scanned) -> None:
    assert all(not p.extract_text().strip() for p in PdfReader(io.BytesIO(scan.pdf)).pages)


def test_scan_is_deterministic_per_seed(sat: Rendered, scan: Scanned) -> None:
    assert degrade(sat, "medium").pdf == scan.pdf
    assert degrade(sat, "medium", seed=1).pdf != scan.pdf
    meta = PdfReader(io.BytesIO(scan.pdf)).metadata
    assert meta is not None
    assert meta["/CreationDate"] == f"D:{sat.issued:%Y%m%d}000000Z"


def test_validator_catches_a_quad_without_ink(scan: Scanned) -> None:
    serial = scan.placed["serial"]
    assert serial.quad is not None
    blank = tuple((x, y + 600) for x, y in serial.quad)  # lower margin of page 1
    placed = {**scan.placed, "serial": replace(serial, quad=blank)}
    assert scan_problems(replace(scan, placed=placed)) == [
        "SAT-TP201_rev0.pdf serial: no ink in its quad on page 1"
    ]


def test_only_paper_documents_are_scanned() -> None:
    eq = load(TP201)
    assert {(d.id, d.scan) for d in eq.documents if d.scan} == {
        ("SAT-TP201", "medium"),
        ("MTC-TP201-01", "medium"),
        ("KAL-2025-0412", "light"),
        ("KAL-2026-0057", "light"),
        ("CAL-TP201-01", "light"),
    }
