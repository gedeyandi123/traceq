"""Local OCR spike on a scan (thin-slice spec #29, ticket #31; ADR 0004). Not product code.

Two steps, run in two environments, because the candidates' dependencies stay out of the
project's lock file:

1. ``read``: run one candidate on a scanned PDF, CPU only, in an environment that has the
   candidate installed (plus ``pypdfium2`` and ``psutil``)::

       python -I scripts/ocr_spike.py read pp-ocrv5 SAT-TP201_rev0.pdf out/pp-ocrv5.json
       python -I scripts/ocr_spike.py read paddleocr-vl SAT-TP201_rev0.pdf out/vl.json
       python -I scripts/ocr_spike.py read haiku SAT-TP201_rev0.pdf out/haiku.json

   It writes what the candidate read as submission ``ocr`` entries (pt, top-left origin),
   with the model version, model load time, seconds per page and the process's peak RAM.
   ``haiku`` (Claude vision, a comparison only) needs the ``anthropic`` package and
   credentials, and makes one Messages API call per page.

2. ``score``: in the project environment, score each candidate file with the existing OCR
   scorer and print a Markdown table and the verdict against the spec's thresholds::

       uv run python scripts/ocr_spike.py score world/tp201.yaml out/*.json

The document id and revision come from the file name (``<doc>_rev<n>.pdf``), as in the
released corpus.
"""

from __future__ import annotations

import argparse
import base64
import html
import importlib
import io
import json
import re
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

Quad = list[list[float]]

# The spec's verdict thresholds (#29, "OCR: spike, then no port").
MAX_EXACT_GAP = 8  # of all entries
MAX_NUMBER_DATE_GAP = 3  # of the number and date entries
MAX_SECONDS_PER_PAGE = 60.0
MAX_PEAK_RAM_GB = 4.0

HAIKU_MODEL = "claude-haiku-5-5"
HAIKU_USD_PER_MTOK = (0.10, 0.50)  # input, output; standard rate, no Batch discount
HAIKU_PROMPT = """This is one page of a scanned, partly handwritten test record.
Transcribe every handwritten entry on the page, one entry per table cell or field; skip the
printed text. Copy each entry exactly as written: keep the decimal and thousands separators,
units, letter case and date format as they appear; do not normalise or interpret values.
For each entry give its bounding box in pixels of this image as [x0, y0, x1, y1].
Answer with JSON only: {"entries": [{"text": "...", "box": [x0, y0, x1, y1]}]}"""


def _module(name: str) -> Any:
    """Import a candidate's package at run time: it is not a project dependency."""
    return importlib.import_module(name)


def doc_rev(pdf: Path) -> tuple[str, int]:
    m = re.fullmatch(r"(.+)_rev(\d+)", pdf.stem)
    if not m:
        raise SystemExit(f"expected <doc>_rev<n>.pdf, got {pdf.name}")
    return m.group(1), int(m.group(2))


def pages(pdf: Path) -> list[tuple[Any, float]]:
    """Each page as a PIL image at the scan's own resolution, with that dpi."""
    pdfium = _module("pypdfium2")
    raw = _module("pypdfium2.raw")
    out = []
    for page in pdfium.PdfDocument(str(pdf)):
        width_pt = page.get_width()
        images = list(page.get_objects(filter=[raw.FPDF_PAGEOBJ_IMAGE]))
        dpi = images[0].get_px_size()[0] / width_pt * 72 if images else 150.0
        out.append((page.render(scale=dpi / 72).to_pil().convert("RGB"), dpi))
    return out


def _quad_pt(points: Sequence[Sequence[float]], dpi: float) -> Quad:
    return [[round(float(x) * 72 / dpi, 2), round(float(y) * 72 / dpi, 2)] for x, y in points]


def _box_quad(x0: float, y0: float, x1: float, y1: float) -> list[list[float]]:
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def _peak_ram_bytes() -> int:
    info = _module("psutil").Process().memory_info()
    return int(getattr(info, "peak_wset", 0) or getattr(info, "rss", 0))


def _version(dist: str) -> str:
    from importlib.metadata import version

    return version(dist)


# --- candidates: each returns (model, version, read_page) where read_page(image, dpi) gives
# entries as {"text", "quad" | None} in pt, plus usage for metered candidates.

Reader = Callable[[Any, float], tuple[list[dict[str, Any]], dict[str, int]]]


def rapidocr(ocr_version: str, model_type: str) -> tuple[str, str, Reader]:
    """PP-OCR detection + recognition (ONNX) through RapidOCR: one entry per text line.
    Pinned explicitly, since RapidOCR's default model changes between its releases."""
    np = _module("numpy")
    ro = _module("rapidocr")
    version, kind = ro.OCRVersion(ocr_version), ro.ModelType(model_type)
    engine = ro.RapidOCR(
        params={
            "Det.ocr_version": version,
            "Det.model_type": kind,
            "Rec.ocr_version": version,
            "Rec.model_type": kind,
        }
    )

    def read(image: Any, dpi: float) -> tuple[list[dict[str, Any]], dict[str, int]]:
        r = engine(np.asarray(image))
        boxes = [] if r.boxes is None else r.boxes
        return [
            {"text": str(t), "quad": _quad_pt(b, dpi)}
            for b, t in zip(boxes, r.txts or (), strict=True)
        ], {}

    return f"{ocr_version} {model_type} via RapidOCR", f"rapidocr {_version('rapidocr')}", read


_CELL = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S)
_TAG = re.compile(r"<[^>]+>")


def _cells(content: str) -> list[str]:
    """Table blocks come back as HTML: one entry per cell, else one per line."""
    parts = _CELL.findall(content) if "<t" in content else content.splitlines()
    out = []
    for p in parts:
        text = " ".join(html.unescape(_TAG.sub(" ", p)).split())
        if text:
            out.append(text)
    return out


def paddleocr_vl() -> tuple[str, str, Reader]:
    """PaddleOCR-VL (layout detection + 0.9B VLM). Boxes are layout blocks, not entries, so
    a table cell has no quad of its own and is matched by text."""
    pipeline = _module("paddleocr").PaddleOCRVL()
    np = _module("numpy")

    def read(image: Any, dpi: float) -> tuple[list[dict[str, Any]], dict[str, int]]:
        entries: list[dict[str, Any]] = []
        for res in pipeline.predict(np.asarray(image)[:, :, ::-1]):
            data = res.json
            for block in data.get("res", data)["parsing_res_list"]:
                cells = _cells(str(block.get("block_content", "")))
                x0, y0, x1, y1 = block["block_bbox"]
                quad = _quad_pt(_box_quad(x0, y0, x1, y1), dpi) if len(cells) == 1 else None
                entries += [{"text": c, "quad": quad} for c in cells]
        return entries, {}

    return "PaddleOCR-VL", f"paddleocr {_version('paddleocr')}", read


def haiku() -> tuple[str, str, Reader]:
    """Claude Haiku vision, the comparison: one Messages API call per page."""
    client = _module("anthropic").Anthropic()

    def read(image: Any, dpi: float) -> tuple[list[dict[str, Any]], dict[str, int]]:
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        msg = client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=16000,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": base64.standard_b64encode(buf.getvalue()).decode(),
                            },
                        },
                        {"type": "text", "text": HAIKU_PROMPT},
                    ],
                }
            ],
        )
        if msg.stop_reason != "end_turn":
            raise SystemExit(f"haiku stopped: {msg.stop_reason}")
        text = "".join(b.text for b in msg.content if b.type == "text")
        found = re.search(r"\{.*\}", text, re.S)
        data = json.loads(found.group(0)) if found else {"entries": []}
        entries = []
        for e in data.get("entries", []):
            box = e.get("box")
            quad = _quad_pt(_box_quad(*box), dpi) if box and len(box) == 4 else None
            entries.append({"text": str(e["text"]), "quad": quad})
        usage = {"input_tokens": msg.usage.input_tokens, "output_tokens": msg.usage.output_tokens}
        return entries, usage

    return HAIKU_MODEL, f"anthropic {_version('anthropic')}", read


CANDIDATES: dict[str, Callable[[], tuple[str, str, Reader]]] = {
    "pp-ocrv5": lambda: rapidocr("PP-OCRv5", "mobile"),
    "pp-ocrv6": lambda: rapidocr("PP-OCRv6", "small"),
    "paddleocr-vl": paddleocr_vl,
    "haiku": haiku,
}


def read(candidate: str, pdf: Path, out: Path) -> None:
    doc, rev = doc_rev(pdf)
    scans = pages(pdf)
    t0 = time.perf_counter()
    model, version, reader = CANDIDATES[candidate]()
    load_s = time.perf_counter() - t0
    entries: list[dict[str, Any]] = []
    seconds: list[float] = []
    usage: dict[str, int] = {}
    for n, (image, dpi) in enumerate(scans, 1):
        t = time.perf_counter()
        got, used = reader(image, dpi)
        seconds.append(round(time.perf_counter() - t, 2))
        entries += [{"doc": doc, "rev": rev, "page": n, **e} for e in got]
        for k, v in used.items():
            usage[k] = usage.get(k, 0) + v
    result: dict[str, Any] = {
        "candidate": candidate,
        "model": model,
        "version": version,
        "load_seconds": round(load_s, 2),
        "seconds_per_page": seconds,
        "peak_ram_bytes": _peak_ram_bytes(),
        "ocr": entries,
    }
    if usage:
        i, o = usage.get("input_tokens", 0), usage.get("output_tokens", 0)
        result["usage"] = usage
        result["cost_usd"] = round((i * HAIKU_USD_PER_MTOK[0] + o * HAIKU_USD_PER_MTOK[1]) / 1e6, 5)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{candidate}: {len(entries)} entries, {seconds} s/page, load {load_s:.1f} s -> {out}")


# --- scoring (project environment)


def summary(run: dict[str, Any], world: Path) -> dict[str, Any]:
    sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
    from traceq_dataset.answer_key import load_key
    from traceq_dataset.world import load
    from traceq_eval.ocr import score_ocr
    from traceq_eval.submission import OcrEntry, Submission, System

    eq = load(world)
    key = load_key(Path(__file__).parents[1] / "answer_key" / eq.tag)
    sub = Submission(
        equipment=eq.tag,
        system=System(name=f"ocr-spike/{run['candidate']}", model=run["model"]),
        ocr=tuple(OcrEntry.model_validate(e) for e in run["ocr"]),
    )
    report = score_ocr(sub, key)
    items = report["items"]
    nd = [i for i in items if i["kind"] in ("number", "date")]
    return {
        **run,
        "metrics": report["metrics"],
        "exact": sum(i["exact"] for i in items),
        "n": len(items),
        "exact_nd": sum(i["exact"] for i in nd),
        "n_nd": len(nd),
        "misread": [(i["field"], i["expected"], i["got"]) for i in items if not i["exact"]],
    }


def fits(r: dict[str, Any]) -> bool:
    """Within the spec's time and RAM limits on this CPU."""
    return (
        max(r["seconds_per_page"]) <= MAX_SECONDS_PER_PAGE
        and r["peak_ram_bytes"] / 1e9 <= MAX_PEAK_RAM_GB
    )


def verdict(local: list[dict[str, Any]], ref: dict[str, Any] | None) -> list[str]:
    """Reasons to replace ADR 0004, from the best local candidate: the most exact matches
    among those within the time and RAM limits (any candidate if none is).

    Without the Haiku run, Haiku is assumed perfect: if the best local candidate stays
    within the gaps even then, the verdict does not depend on the comparison."""
    best = max(local, key=lambda r: (fits(r), r["exact"], r["exact_nd"]))
    reasons = []
    if max(best["seconds_per_page"]) > MAX_SECONDS_PER_PAGE:
        reasons.append(f"{best['candidate']} needs > {MAX_SECONDS_PER_PAGE:.0f} s per page")
    if best["peak_ram_bytes"] / 1e9 > MAX_PEAK_RAM_GB:
        reasons.append(f"{best['candidate']} needs > {MAX_PEAK_RAM_GB:.0f} GB peak RAM")
    exact, nd = (ref["exact"], ref["exact_nd"]) if ref else (best["n"], best["n_nd"])
    who = "Haiku" if ref else "a perfect Haiku"
    if exact - best["exact"] >= MAX_EXACT_GAP:
        reasons.append(f"trails {who} by ≥ {MAX_EXACT_GAP} exact matches")
    if nd - best["exact_nd"] >= MAX_NUMBER_DATE_GAP:
        reasons.append(f"trails {who} by ≥ {MAX_NUMBER_DATE_GAP} number and date entries")
    return [f"best local: {best['candidate']} ({best['model']}, {best['version']})", *reasons]


def score(world: Path, files: list[Path]) -> None:
    runs = [summary(json.loads(f.read_text(encoding="utf-8")), world) for f in files]
    print(
        "| Candidate | Exact | Number+date exact | CER | CER numbers | CER dates "
        "| Entry recall | Localisation | s/page | Load s | Peak RAM GB | Cost USD |"
    )
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in runs:
        m = r["metrics"]
        print(
            f"| {r['model']} ({r['version']}) | {r['exact']}/{r['n']} "
            f"| {r['exact_nd']}/{r['n_nd']} | {m['cer']} | {m['cer_by_kind']['number']} "
            f"| {m['cer_by_kind']['date']} | {m['entry_recall']} | {m['localisation_rate']} "
            f"| {', '.join(map(str, r['seconds_per_page']))} | {r['load_seconds']} "
            f"| {r['peak_ram_bytes'] / 1e9:.2f} | {r.get('cost_usd', 0)} |"
        )
    for r in runs:
        print(f"\n{r['candidate']} misread (field: expected -> read):")
        for field, exp, got in r["misread"]:
            print(f"- {field}: {exp!r} -> {got!r}")
    local = [r for r in runs if r["candidate"] != "haiku"]
    ref = next((r for r in runs if r["candidate"] == "haiku"), None)
    lines = verdict(local, ref)
    print("\nVerdict:", "; ".join(lines))
    if ref is None:
        print("No Haiku run: the gaps are taken against a perfect Haiku (an upper bound).")
    print("Replace ADR 0004" if len(lines) > 1 else "Keep ADR 0004")


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="ocr_spike")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("read")
    r.add_argument("candidate", choices=sorted(CANDIDATES))
    r.add_argument("pdf", type=Path)
    r.add_argument("out", type=Path)
    s = sub.add_parser("score")
    s.add_argument("world", type=Path)
    s.add_argument("runs", type=Path, nargs="+")
    a = p.parse_args(argv)
    if a.cmd == "read":
        read(a.candidate, a.pdf, a.out)
    else:
        score(a.world, a.runs)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
