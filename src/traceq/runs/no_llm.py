"""The No-LLM Baseline (#193, ADR 0010): an adapter behind the LLM port that answers every
prompt with regular expressions and keywords over the request text, and no model.

A run with it (``traceq run --llm no-llm``) goes through the same pipeline as a model run:
the citation check, the rules, the Coverage decision table, the missing documents and the
OCR are unchanged. Its scores say how much a plain reader gets from the same documents, so
the LLM's figures have something to be compared with.

Each reader is a general rule, written as for an unseen URS, not tuned to a dataset:

- ``segment``: a line that starts with a requirement number (letters, then a hyphen and
  digits) is one requirement; a leading critical flag (Yes/No, Ya/Tidak) is not its text.
  Unnumbered requirements are not found.
- ``extract``: a range (``20–80``), then a bounding word (at least, maksimal, ``≥``), then a
  material list (made of, terbuat dari), then a type code, then a number; otherwise the
  requirement asks for something to be present.
- ``facts``: a line that starts with a step number and ends with a result word is a step;
  the test is its text up to the last full stop, the acceptance and the observed result the
  rest. Approval and execution dates come from the signature rows; design rows are a name
  followed by a number, Yes/No or a code.
- ``link`` and ``transport``: the steps and rows that share the most words and numbers with
  the requirement; site-only and transport-sensitive by keywords; the area whose name shares
  a word stem with the requirement and its Evidence.
- ``vendor_assessment``, ``record``, ``required_documents``, ``site_rules``: table rows and
  sentences matched by their labels and keywords.
- ``ai_review``: no findings; no rule can judge these issues.
- ``draft``: the Acceptance Criterion is the requirement's own value, only when the request
  carries it with its quote; otherwise none, for a human to set.

Answers cost nothing: 0 tokens, and the run counts no LLM calls.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Callable, Sequence
from typing import Any, cast

from traceq.ai import Request, Response
from traceq.traceability.citations import MAX_QUOTE

MODEL = "no-llm-v1"

Answer = dict[str, Any]

# --- Text pieces ------------------------------------------------------------------------

NUM = r"\d+(?:[.,]\d+)*"
ID = r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-\d+[A-Z]?"
"""A printed number such as a requirement, step or instrument id: ends in hyphen and digits."""
CODE = r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+"
"""A document or instrument id: letters, then hyphenated parts."""
DATE = r"\d{4}-\d{2}-\d{2}|\d{1,2}[-/.](?:\d{1,2}|[A-Za-z]{3})[-/.]\d{4}"
DASH = r"\s*(?:–|—|-|\bto\b|s\.d\.|sampai|hingga)\s*"
RESULT = r"(?i:pass(?:ed)?|fail(?:ed)?|lulus|gagal|ok|nok)"

_PAGE = re.compile(r"Document .+?, page \d+\.\s*<page>\n?(?P<text>.*?)\n?</page>", re.S)
_PAGES = re.compile(r'<page n="(?P<n>\d+)">\n?(?P<text>.*?)\n?</page>', re.S)

_STOP = frozenset(
    [
        "the",
        "and",
        "for",
        "with",
        "its",
        "all",
        "are",
        "from",
        "that",
        "this",
        "each",
        "per",
        "not",
        "any",
        "its",
        "into",
        "than",
        "then",
        "yang",
        "dan",
        "untuk",
        "dengan",
        "pada",
        "dari",
        "atau",
        "dalam",
        "ini",
        "itu",
        "oleh",
        "setiap",
        "semua",
        "dapat",
        "adalah",
        "akan",
        "harus",
        "tidak",
        "juga",
        "serta",
        "saat",
    ]
)
_UNIT_WORDS = {"jam": "h", "menit": "min", "detik": "s", "hour": "h", "hours": "h"}
_NOT_UNITS = frozenset(
    [
        "dan",
        "atau",
        "and",
        "or",
        "di",
        "ke",
        "the",
        "of",
        "to",
        "per",
        "for",
        "at",
        "in",
        "on",
        "is",
        "are",
        "set",
        "dari",
        "pada",
        "x",
        "by",
        "as",
    ]
)
_PRESENT_WORDS = re.compile(
    r"(?i)\b(?:present|functional|yes|ya|ada|berfungsi|available|tersedia|ok)\b"
)
_AVAILABLE = re.compile(
    r"(?i)\b(?:available|supplied|provided|present|tersedia|dilengkapi|equipped)\b"
)
_MIN_WORDS = (
    r"minimal|minimum|min\.|at least|not less than|no less than|sekurang-kurangnya"
    r"|paling sedikit|tidak kurang dari|≥|>="
)
_MAX_WORDS = (
    r"maksimal|maksimum|maximum|max\.|at most|up to|not more than|no more than"
    r"|paling banyak|tidak lebih dari|≤|<="
)
_SITE = re.compile(
    r"(?i)\b(?:pabrik|plant|site|lokasi|ruang(?:an)?|room|gedung|building|utilitas"
    r"|utility|utilities|suplai|supply)\b"
)
_TRANSPORT = re.compile(
    r"(?i)(?:interlock|emergency|darurat|safety|keselamatan|alarm|kontrol|control|kendali"
    r"|software|perangkat lunak|\bhmi\b|\bplc\b|kalibrasi|calibrat|akurasi|accura|presisi"
    r"|precision|kapasitas|capacity|output|kinerja|performance|beban|\bload|overload)"
)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip()


def _page_text(user: str) -> str:
    m = _PAGE.search(user)
    return "" if m is None else m["text"]


def _pages(user: str) -> list[tuple[int, str]]:
    return [(int(m["n"]), m["text"]) for m in _PAGES.finditer(user)]


def _lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _clip(line: str, end: int | None = None) -> str:
    """The line, or its start up to ``end`` when the whole line is too long to quote."""
    if len(_norm(line)) <= MAX_QUOTE or end is None:
        return line
    return line[:end]


def number(token: str) -> float:
    """A printed number. One separator before exactly three digits groups thousands;
    otherwise it is the decimal point."""
    seps = [c for c in token if c in ".,"]
    if not seps:
        return float(token)
    if len(set(seps)) == 2:
        decimal = token[max(token.rfind("."), token.rfind(","))]
        grouping = "," if decimal == "." else "."
        return float(token.replace(grouping, "").replace(decimal, "."))
    sep = seps[0]
    if len(seps) > 1 or len(token) - token.index(sep) - 1 == 3:
        return float(token.replace(sep, ""))
    return float(token.replace(sep, "."))


def _canonical(token: str) -> str:
    return f"{number(token):g}"


def unit(token: str | None) -> str | None:
    """A unit symbol printed after a number, in English where Indonesian names a unit of
    time; ``None`` when the word after the number is not a unit."""
    if not token:
        return None
    t = token.rstrip(".,;:")
    if not t or t.casefold() in _NOT_UNITS or t[0].isdigit():
        return None
    parts = [_UNIT_WORDS.get(p.casefold(), p) for p in t.split("/")]
    symbolic = any(c in t for c in "/°µ%³²")
    if symbolic or t.casefold() in _UNIT_WORDS or (len(t) <= 4 and t.isalpha()):
        return "/".join(parts)
    return None


def _tokens(text: str) -> set[str]:
    """Content words and numbers, for overlap between a requirement and its Evidence."""
    t = unicodedata.normalize("NFKC", text).casefold()
    numbers = {_canonical(n) for n in re.findall(NUM, t)}
    words = {w for w in re.findall(r"[^\W\d_]{3,}", t) if w not in _STOP}
    return numbers | words


def _dump(answer: Answer) -> str:
    return json.dumps(answer, ensure_ascii=False)


# --- Values -----------------------------------------------------------------------------

_UNIT_AFTER = r"(?:\s*(?P<unit>[^\s\d,;()][^\s,;()]*))?"
_RANGE = re.compile(rf"(?<![\w.,])(?P<lo>{NUM}){DASH}(?P<hi>{NUM}){_UNIT_AFTER}")
_LOWER = re.compile(rf"(?i:{_MIN_WORDS})\s*±?\s*(?P<n>{NUM}){_UNIT_AFTER}")
_UPPER = re.compile(rf"(?i:{_MAX_WORDS})\s*±?\s*(?P<n>{NUM}){_UNIT_AFTER}")
_MATERIAL = re.compile(r"(?i:terbuat dari|dibuat dari|made of|made from)\s+(?P<list>[^.;]+)")
_TYPE = re.compile(
    r"(?i:\btipe|\btype|\bjenis)\s+(?P<code>[A-Z0-9][A-Z0-9-]*(?: [A-Z0-9][A-Z0-9-]*)*)"
)
_NUMBER = re.compile(rf"(?<![\w.,])(?P<n>{NUM}){_UNIT_AFTER}")


def _empty_value() -> Answer:
    return {
        "kind": "none",
        "min": None,
        "max": None,
        "number": None,
        "unit": None,
        "allowed": [],
        "text": None,
    }


def required_value(text: str) -> Answer:
    """The value a requirement sentence states, in the ``extract`` schema without a quote."""
    v = _empty_value()
    if m := _RANGE.search(text):
        v.update(kind="range", min=number(m["lo"]), max=number(m["hi"]), unit=unit(m["unit"]))
    elif m := _LOWER.search(text):
        v.update(kind="range", min=number(m["n"]), unit=unit(m["unit"]))
    elif m := _UPPER.search(text):
        v.update(kind="range", max=number(m["n"]), unit=unit(m["unit"]))
    elif m := _MATERIAL.search(text):
        allowed = [a.strip() for a in re.split(r"\s+(?:atau|or)\s+|\s*,\s*|\s*/\s*", m["list"])]
        v.update(kind="one_of", allowed=[a for a in allowed if a])
    elif m := _TYPE.search(text):
        v.update(kind="text", text=m["code"])
    elif (m := _NUMBER.search(text)) and (unit(m["unit"]) or not _AVAILABLE.search(text)):
        v.update(kind="number", number=number(m["n"]), unit=unit(m["unit"]))
    else:
        v.update(kind="present")
    return v


def _observed_value(observed: str, result: str) -> Answer:
    """An observation in the ``facts`` value schema."""
    v: Answer = {
        "kind": "none",
        "min": None,
        "max": None,
        "number": None,
        "unit": None,
        "text": None,
        "present": None,
    }
    if m := _RANGE.search(observed):
        v.update(kind="range", min=number(m["lo"]), max=number(m["hi"]), unit=unit(m["unit"]))
    elif m := _NUMBER.search(observed):
        v.update(kind="number", number=number(m["n"]), unit=unit(m["unit"]))
    elif _PRESENT_WORDS.search(observed) or re.fullmatch(
        r"(?i)no|tidak|absent|tidak ada", observed
    ):
        v.update(kind="present", present=result == "pass")
    elif observed.strip():
        v.update(kind="text", text=observed.strip())
    return v


# --- URS --------------------------------------------------------------------------------

_REQUIREMENT = re.compile(rf"^(?P<id>{ID})\s+(?:(?:Ya|Tidak|Yes|No)\s+)?(?P<text>\S.*)$")


def segment(user: str) -> Answer:
    found: list[Answer] = []
    for line in _lines(_page_text(user)):
        if m := _REQUIREMENT.match(line):
            text = m["text"]
            quote = line if len(_norm(line)) <= MAX_QUOTE else text[:MAX_QUOTE]
            found.append({"id": m["id"], "text": text, "quote": quote})
    return {"requirements": found}


def extract(user: str) -> Answer:
    head, _, _ = user.partition("\n\n")
    try:
        text = str(json.loads(head)["requirement"])
    except (ValueError, KeyError, TypeError):
        return {**_empty_value(), "quote": ""}
    return {**required_value(text), "quote": text[:MAX_QUOTE]}


# --- Vendor documents -------------------------------------------------------------------

_STEP = re.compile(rf"^(?P<step>{ID})\s+(?P<body>.+?)\s+(?P<result>{RESULT})$")
_ROLE = {
    "prepared": r"prepared by|disusun oleh|dibuat oleh",
    "checked": r"checked by|reviewed by|diperiksa oleh",
    "approved": r"approved by|disetujui oleh",
    "executed": r"executed by|performed by|dilaksanakan oleh|dieksekusi oleh",
    "witnessed": r"witnessed by|disaksikan oleh",
    "other": r"calibrated by|verified by|dikalibrasi oleh",
}
_SITE_SIGNER = re.compile(r"(?i)\b(?:site|customer|pelanggan)\b")


def _split_step(body: str) -> tuple[str, str, str]:
    """Test, acceptance and observed result of a step line without its number and result."""
    i = body.rfind(". ")
    test, tail = (body[: i + 1], body[i + 2 :]) if i >= 0 else (body, "")
    toks = tail.split()
    n = len(toks)
    if not toks:
        return test, "", ""
    if n % 2 == 0 and toks[: n // 2] == toks[n // 2 :]:
        half = " ".join(toks[: n // 2])
        return test, half, half
    digits = [k for k, t in enumerate(toks) if t[0].isdigit()]
    if digits:
        k = digits[-1]
        if k >= 2 and toks[k - 1] in ("–", "-", "to") and toks[k - 2][0].isdigit():
            k -= 2
        acc = toks[:k]
        while acc and re.fullmatch(CODE, acc[-1]):
            acc.pop()
        observed = " ".join(toks[k:])
        return test, " ".join(acc) or observed, observed
    if n % 2 == 0:
        return test, " ".join(toks[: n // 2]), " ".join(toks[n // 2 :])
    return test, tail, tail


def _steps(text: str) -> list[Answer]:
    out: list[Answer] = []
    for line in _lines(text):
        m = _STEP.match(line)
        if m is None:
            continue
        test, acceptance, observed = _split_step(m["body"])
        result = "pass" if m["result"].casefold() in ("pass", "passed", "lulus", "ok") else "fail"
        end = line.rfind(observed) + len(observed) if observed else None
        out.append(
            {
                "step": m["step"],
                "test": test,
                "acceptance": acceptance,
                "observed": observed,
                "result": result,
                "value": _observed_value(observed, result),
                "quote": _clip(line, end),
            }
        )
    return out


def _role(line: str) -> tuple[str, str, str] | None:
    """The role code, the role label as printed and the rest of a signature row."""
    for role, pattern in _ROLE.items():
        if m := re.match(rf"(?i:{pattern})\b", line):
            return role, m[0], line[m.end() :].strip()
    return None


def _signed_date(text: str, roles: tuple[str, ...], site: bool) -> Answer | None:
    for line in _lines(text):
        r = _role(line)
        if r is None or r[0] not in roles:
            continue
        dates = re.findall(DATE, r[2])
        if dates and (not site or _SITE_SIGNER.search(r[2])):
            return {"date": dates[-1], "quote": _clip(line, line.rfind(dates[-1]) + len(dates[-1]))}
    return None


_YES_NO = re.compile(r"^(?P<name>.*(?:[^\W\d_]|\)))\s+(?P<v>Yes|No|Ya|Tidak)$")
# The name ends in a lower-case letter or a bracket, so a code before the number ("SS 304")
# is read as a code row, not as a name.
_ROW_NUMBER = re.compile(
    rf"^(?P<name>.*?(?:[a-z]|\)))\s+(?P<v>±?\s*{NUM}(?:{DASH}{NUM})?(?:\s*[^\s\d]+){{0,2}})$"
)
_ROW_CODE = re.compile(
    r"^(?P<name>[A-Z][a-z][^\d]*?)\s+(?P<v>[A-Z0-9][A-Z0-9.\-]*(?:\s+[A-Z0-9][A-Z0-9.\-]*)*)$"
)


def _rows(text: str) -> list[Answer]:
    out: list[Answer] = []
    for line in _lines(text):
        if re.search(DATE, line) or _STEP.match(line) or _role(line):
            continue
        if m := _YES_NO.match(line):
            v = _observed_value("", "pass")
            v.update(kind="present", present=m["v"] in ("Yes", "Ya"))
        elif m := _ROW_NUMBER.match(line):
            v = _observed_value(m["v"], "pass")
        elif m := _ROW_CODE.match(line):
            v = _observed_value("", "pass")
            v.update(kind="text", text=m["v"])
        else:
            continue
        out.append({"name": m["name"], "printed": m["v"], "value": v, "quote": m["v"]})
    return out


def facts(user: str) -> Answer:
    text = _page_text(user)
    return {
        "site_approved_on": _signed_date(text, ("approved",), site=True),
        "executed_on": _signed_date(text, ("executed",), site=False),
        "steps": _steps(text),
        "rows": _rows(text),
    }


def _area(areas: Sequence[str], text: str) -> str | None:
    """The one area whose name shares the most word stems with ``text``; ``None`` on a tie
    or when none shares any."""

    def stems(s: str) -> set[str]:
        return {w[:5] for w in _tokens(s) if w.isalpha() and len(w) >= 4}

    have = stems(text)
    scored = sorted(((len(stems(a) & have), a) for a in areas), reverse=True)
    if not scored or scored[0][0] == 0 or (len(scored) > 1 and scored[1][0] == scored[0][0]):
        return None
    return scored[0][1]


def _best(scores: dict[str, int]) -> list[str]:
    """Ids sharing at least two words with the requirement, and within one of the best."""
    top = max(scores.values(), default=0)
    return [i for i, s in scores.items() if s >= 2 and s >= top - 1]


def link(user: str) -> Answer:
    try:
        j: dict[str, Any] = json.loads(user)
        text = str(j["requirement"]["text"])
        steps: list[dict[str, Any]] = list(j.get("steps", []))
        rows: list[dict[str, Any]] = list(j.get("rows", []))
        areas = [str(a) for a in j.get("areas", [])]
    except (ValueError, KeyError, TypeError):
        return {
            "steps": [],
            "rows": [],
            "site_only": False,
            "transport_sensitive": False,
            "area": None,
        }
    want = _tokens(text)
    step_text = {str(s["id"]): f"{s.get('test', '')} {s.get('acceptance', '')}" for s in steps}
    row_text = {str(r["id"]): f"{r.get('name', '')} {r.get('value', '')}" for r in rows}
    linked_steps = _best({i: len(_tokens(t) & want) for i, t in step_text.items()})
    linked_rows = _best({i: len(_tokens(t) & want) for i, t in row_text.items()})
    evidence = " ".join(
        [text, *(step_text[i] for i in linked_steps), *(row_text[i] for i in linked_rows)]
    )
    return {
        "steps": linked_steps,
        "rows": linked_rows,
        "site_only": bool(_SITE.search(text)),
        "transport_sensitive": bool(_TRANSPORT.search(text)),
        "area": _area(areas, evidence),
    }


_ISSUED = re.compile(
    r"(?i:tanggal berlaku|tanggal terbit|tanggal|date of issue|issue date|issued|date)"
    rf"\s*:?\s*(?P<d>{DATE})"
)
_RATED = re.compile(r"^(?P<area>.+?)\s+(?P<mark>Ya|Tidak|Yes|No)(?:\s|$)")


def vendor_assessment(user: str) -> Answer:
    assessed: Answer | None = None
    areas: list[Answer] = []
    for n, text in _pages(user):
        in_table = False
        for line in _lines(text):
            if assessed is None and (m := _ISSUED.search(line)):
                assessed = {"date": m["d"], "page": n, "quote": _clip(line, m.end())}
            if re.search(r"\bArea\b", line) and not _RATED.match(line):
                in_table = True
                continue
            if not in_table:
                continue
            m = _RATED.match(line)
            if m is None or re.match(r"\d+\.\s", line):
                in_table = False
                continue
            areas.append(
                {
                    "area": m["area"],
                    "mark": m["mark"],
                    "relied": m["mark"] in ("Ya", "Yes"),
                    "page": n,
                    "quote": _clip(line, m.end("mark")),
                }
            )
    return {"assessed_on": assessed, "areas": areas}


# --- Records ----------------------------------------------------------------------------

_NAME = re.compile(r"^(?P<name>[A-Z][a-z'\-]+(?:\s+[A-Z][a-z'\-]+)?)\b")
_ASSET = re.compile(
    rf"(?i:asset id|instrument id|equipment id|id alat)\s+(?P<id>\S+)[\s\S]{{0,150}}?"
    rf"(?i:valid until|due date|cal\. due|calibration due|berlaku s\.d\.|berlaku sampai)\s+"
    rf"(?P<d>{DATE})"
)
_INSTRUMENT_ROW = re.compile(rf"^(?P<id>{CODE})\s.*\s(?P<d>{DATE})$")
_INSTRUMENT_REF = re.compile(r"\b[A-Z]{2,}[A-Z0-9]*-\d+[A-Z0-9]*\b")
_DEVIATION = re.compile(r"\b(?:DEV|NCR|DEVIASI)-[A-Z0-9-]*\d\b")


def _signature(line: str) -> Answer | None:
    r = _role(line)
    if r is None:
        return None
    role, printed, rest = r
    m = _NAME.match(rest)
    name = "" if m is None else m["name"]
    dates = re.findall(DATE, rest)
    date = dates[-1] if dates else ""
    surname = name.split()[-1] if name else ""
    after = rest[len(name) :]
    signed = bool(name) and bool(
        re.search(r"(?i)signed|ditandatangani|tanda tangan", rest)
        or (surname and re.search(rf"\b{re.escape(surname)}\b", after))
    )
    end = line.rfind(date) + len(date) if date else None
    return {
        "role_printed": printed,
        "role": role,
        "site": bool(_SITE_SIGNER.search(rest)),
        "name": name,
        "signed": signed,
        "date": date,
        "quote": _clip(line, end),
    }


def record(user: str) -> Answer:
    text = _page_text(user)
    lines = _lines(text)
    signatures = [s for line in lines if (s := _signature(line)) is not None]
    instruments: list[Answer] = [
        {"id": m["id"], "valid_until": m["d"], "quote": _norm(m[0])} for m in _ASSET.finditer(text)
    ]
    if re.search(r"(?i)\bdue\b|valid until|berlaku", text):
        for line in lines:
            if (m := _INSTRUMENT_ROW.match(line)) and not _role(line):
                instruments.append(
                    {"id": m["id"], "valid_until": m["d"], "quote": _clip(line, m.end("d"))}
                )
    uses: list[Answer] = []
    step_ids: list[str] = []
    for line in lines:
        m = re.match(rf"^(?P<step>{ID})\s+(?P<body>.+)$", line)
        if m is None or _INSTRUMENT_ROW.match(line):
            continue
        step_ids.append(m["step"])
        refs = [r for r in _INSTRUMENT_REF.findall(m["body"]) if r != m["step"]]
        if refs:
            end = line.rfind(refs[-1]) + len(refs[-1])
            uses.append({"step": m["step"], "instruments": refs, "quote": line[:end]})
    deviations: list[Answer] = []
    for line in lines:
        for d in _DEVIATION.findall(line):
            steps = [s for s in step_ids if s in line and s != d]
            deviations.append({"id": d, "steps": steps, "quote": _clip(line)})
    return {
        "signatures": signatures,
        "instruments": instruments,
        "step_instruments": uses,
        "deviations": deviations,
        "calculations": [],
    }


# --- Governing documents ----------------------------------------------------------------

_ANNEX = re.compile(r"(?i:lampiran|annex|appendix)\b.*?(?P<tag>\b[A-Z]{1,5}-\d{2,5}[A-Z]?\b)")
_ANNEX_ROW = re.compile(
    rf"^(?P<doc>{CODE})\s+(?P<type>.+?)\s+(?P<stage>Desain|Design|FAT|SAT|IQ|OQ)$"
)
_ANNEX_END = re.compile(r"(?i)riwayat revisi|revision history|pengesahan|approval")
_STAGES = {"Desain": "design", "Design": "design"}
_DOC_TYPES = (
    ("material_certificate", r"material"),
    ("calibration_certificate", r"kalibrasi|calibration"),
    ("urs", r"kebutuhan pengguna|user requirement|\bURS\b|\bSKP\b"),
    ("risk_assessment", r"risiko|risk|fmea"),
    ("dq_report", r"kualifikasi desain|design qualification|\bDQ\b"),
    ("functional_spec", r"fungsional|functional"),
    ("datasheet", r"\bdata"),
    ("fat", r"\bFAT\b"),
    ("sat", r"\bSAT\b"),
    ("iq_protocol", r"\bIQ\b|instalasi|installation"),
    ("oq_protocol", r"\bOQ\b|operasional|operational"),
)


def _doc_type(printed: str) -> str:
    return next((t for t, p in _DOC_TYPES if re.search(rf"(?i:{p})", printed)), "other")


def required_documents(user: str) -> Answer:
    annexes: list[Answer] = []
    current: Answer | None = None
    for n, text in _pages(user):
        for line in _lines(text):
            if m := _ANNEX.search(line):
                current = {
                    "equipment": m["tag"],
                    "page": n,
                    "quote": _clip(line, m.end()),
                    "rows": [],
                }
                annexes.append(current)
            elif current is not None and _ANNEX_END.search(line):
                current = None
            elif current is not None and (m := _ANNEX_ROW.match(line)):
                current["rows"].append(
                    {
                        "doc_id": m["doc"],
                        "type_printed": m["type"],
                        "type": _doc_type(m["type"]),
                        "stage_printed": m["stage"],
                        "stage": _STAGES.get(m["stage"], m["stage"]),
                        "page": n,
                        "quote": _clip(line),
                    }
                )
    return {"annexes": annexes}


_NEG = r"\b(?:not|never|tidak|bukan)\b"
_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "signature_name_and_date",
        (r"signature|tanda tangan|ditandatangani", r"\bnam[ea]", r"\bdate|tanggal"),
    ),
    (
        "vendor_protocol_approved_before_execution",
        (r"approv|disetujui|persetujuan", r"before|sebelum|prior", r"protocol|protokol"),
    ),
    (
        "preparer_not_approver",
        (r"prepar|penyusun|disusun|author", r"approv|menyetujui|penyetuju", _NEG),
    ),
    (
        "checker_not_approver",
        (r"checker|reviewer|pemeriksa", r"approv|penyetuju", rf"{_NEG}|different|berbeda"),
    ),
    ("performer_not_witness", (r"perform|execut|pelaksana", r"witness|saksi", _NEG)),
)


def site_rules(user: str) -> Answer:
    found: dict[str, Answer] = {}
    for n, text in _pages(user):
        prose = [line for line in _lines(text) if line.endswith(".")]
        for sentence in (s for line in prose for s in re.split(r"(?<=\.)\s+", line)):
            clauses = [c.strip() for c in sentence.split(", ")]
            for part in [*clauses, sentence]:
                for rule, needs in _RULES:
                    if rule not in found and all(re.search(rf"(?i){p}", part) for p in needs):
                        found[rule] = {"rule": rule, "page": n, "quote": part[:MAX_QUOTE]}
    return {"rules": [found[r] for r, _ in _RULES if r in found]}


def ai_review(_user: str) -> Answer:
    return {"findings": []}


# --- Drafting ---------------------------------------------------------------------------


def _acceptance(value: dict[str, Any]) -> Answer:
    a = _empty_value()
    match value.get("type"):
        case "range":
            a.update(
                kind="range", min=value.get("min"), max=value.get("max"), unit=value.get("unit")
            )
        case "number":
            a.update(kind="number", number=value.get("value"), unit=value.get("unit"))
        case "one_of":
            a.update(kind="one_of", allowed=list(value.get("allowed", [])))
        case "text":
            a.update(kind="text", text=value.get("value"))
        case "present":
            a.update(kind="present")
        case _:
            pass
    return a


def draft(user: str) -> Answer:
    try:
        req: dict[str, Any] = json.loads(user)["requirement"]
    except (ValueError, KeyError, TypeError):
        req = {}
    value: object = req.get("value")
    cited: object = req.get("value_citation")
    acceptance, source = _empty_value(), None
    if isinstance(value, dict) and isinstance(cited, dict):
        c = cast(dict[str, Any], cited)
        acceptance = _acceptance(cast(dict[str, Any], value))
        source = {k: c.get(k) for k in ("doc", "rev", "page", "quote")}
    return {
        "description": f"Verify the requirement: {req.get('text', '')}",
        "method": "Test at the site as the requirement states and record the result.",
        "instrument": None,
        "acceptance": acceptance,
        "acceptance_source": source,
    }


READERS: dict[str, Callable[[str], Answer]] = {
    "segment": segment,
    "extract": extract,
    "facts": facts,
    "link": link,
    "transport": link,
    "vendor_assessment": vendor_assessment,
    "record": record,
    "required_documents": required_documents,
    "site_rules": site_rules,
    "ai_review": ai_review,
    "draft": draft,
}


class NoLLM:
    """The ``LLM`` port answered by the readers above."""

    @property
    def model(self) -> str:
        return MODEL

    def complete(self, requests: Sequence[Request]) -> list[Response]:
        out: list[Response] = []
        for r in requests:
            reader = READERS.get(r.prompt.name)
            if reader is None:
                raise ValueError(f"the No-LLM Baseline has no reader for prompt {r.prompt.name!r}")
            out.append(Response(_dump(reader(r.user)), MODEL, 0, 0))
        return out
