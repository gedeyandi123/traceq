"""AST and regex floor guards: no unapproved suppressions, stubs, or broad silent excepts."""

from __future__ import annotations

import ast
import re
from datetime import date
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC_ROOT = _REPO_ROOT / "src"
_WEB_SRC_ROOT = _REPO_ROOT / "web" / "src"

_GENERATED_WEB_FILES: frozenset[str] = frozenset(
    {
        "web/src/api/schema.ts",
        "web/src/api/eval-schema.ts",
    }
)

_SUPPRESSION_RE = re.compile(
    r"(#\s*noqa\b|#\s*type:\s*ignore\b|#\s*pyright:\s*ignore\b|"
    r"@ts-ignore\b|@ts-expect-error\b|eslint-disable\b)"
)

_TS_NOT_IMPLEMENTED_RE = re.compile(
    r"""throw\s+new\s+Error\s*\(\s*['"`]Not\s+implemented""",
    re.IGNORECASE,
)

# Approved suppressions must state a reason and an expiry date.
_SUPPRESSION_ALLOWLIST: dict[str, tuple[str, date]] = {
    "src/traceq_dataset/degrade.py": ("pypdfium2 render(scale=...) stub typing", date(2027, 6, 1)),
    "src/traceq_dataset/validate.py": ("pypdfium2 render(scale=...) stub typing", date(2027, 6, 1)),
}

# Intentional NotImplementedError guards (e.g. unsupported format) with reason and expiry.
_NOT_IMPLEMENTED_ALLOWLIST: dict[str, tuple[str, date]] = {
    "src/traceq/documents/corpus.py": (
        "Intentional unsupported-format guard for non-readable document formats",
        date(2027, 6, 1),
    ),
}


def find_unapproved_suppressions(
    text: str, rel_path: str, allowlist: dict[str, tuple[str, date]]
) -> list[str]:
    if rel_path in allowlist:
        return []
    hits: list[str] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        match = _SUPPRESSION_RE.search(line)
        if match:
            hits.append(f"{rel_path}:{lineno}: unapproved suppression '{match.group(1)}'")
    return hits


def _is_broad_silent_except(handler: ast.ExceptHandler) -> bool:
    if len(handler.body) != 1 or not isinstance(handler.body[0], ast.Pass):
        return False
    if handler.type is None:
        return True
    if isinstance(handler.type, ast.Name):
        return handler.type.id in {"Exception", "BaseException"}
    if isinstance(handler.type, ast.Tuple):
        return any(
            isinstance(elt, ast.Name) and elt.id in {"Exception", "BaseException"}
            for elt in handler.type.elts
        )
    return False


def find_python_stubs_and_silent_excepts(
    text: str, rel_path: str, allow_not_impl: bool = False
) -> list[str]:
    tree = ast.parse(text, filename=rel_path)
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Raise) and node.exc is not None and not allow_not_impl:
            is_not_impl = (
                isinstance(node.exc, ast.Name) and node.exc.id == "NotImplementedError"
            ) or (
                isinstance(node.exc, ast.Call)
                and isinstance(node.exc.func, ast.Name)
                and node.exc.func.id == "NotImplementedError"
            )
            if is_not_impl:
                hits.append(f"{rel_path}:{node.lineno}: raise NotImplementedError")
        elif isinstance(node, ast.ExceptHandler) and _is_broad_silent_except(node):
            hits.append(f"{rel_path}:{node.lineno}: broad/bare silent except: pass")
    return hits


def _iter_source_files() -> list[Path]:
    py_files = sorted(_SRC_ROOT.rglob("*.py"))
    web_files = sorted(
        p
        for p in _WEB_SRC_ROOT.rglob("*")
        if p.is_file()
        and p.suffix in {".ts", ".tsx", ".js", ".jsx"}
        and p.relative_to(_REPO_ROOT).as_posix() not in _GENERATED_WEB_FILES
    )
    return [*py_files, *web_files]


def test_suppression_allowlist_has_no_expired_entries() -> None:
    today = date.today()
    expired = [
        f"{path} (expired {expires.isoformat()}: {reason})"
        for allowlist in (_SUPPRESSION_ALLOWLIST, _NOT_IMPLEMENTED_ALLOWLIST)
        for path, (reason, expires) in allowlist.items()
        if today > expires
    ]
    assert not expired, "Expired entries in allowlists:\n" + "\n".join(expired)


def test_no_unapproved_suppression_comments() -> None:
    hits: list[str] = []
    for file_path in _iter_source_files():
        rel_path = file_path.relative_to(_REPO_ROOT).as_posix()
        text = file_path.read_text(encoding="utf-8")
        hits.extend(find_unapproved_suppressions(text, rel_path, _SUPPRESSION_ALLOWLIST))
    assert not hits, (
        "New suppression comments require an allowlist entry with reason and expiry:\n"
        + "\n".join(hits)
    )


def test_no_unimplemented_stubs_or_broad_silent_excepts() -> None:
    hits: list[str] = []
    for py_file in sorted(_SRC_ROOT.rglob("*.py")):
        rel_path = py_file.relative_to(_REPO_ROOT).as_posix()
        hits.extend(
            find_python_stubs_and_silent_excepts(
                py_file.read_text(encoding="utf-8"),
                rel_path,
                allow_not_impl=rel_path in _NOT_IMPLEMENTED_ALLOWLIST,
            )
        )

    for web_file in sorted(
        p
        for p in _WEB_SRC_ROOT.rglob("*")
        if p.is_file()
        and p.suffix in {".ts", ".tsx", ".js", ".jsx"}
        and p.relative_to(_REPO_ROOT).as_posix() not in _GENERATED_WEB_FILES
    ):
        rel_path = web_file.relative_to(_REPO_ROOT).as_posix()
        for lineno, line in enumerate(web_file.read_text(encoding="utf-8").splitlines(), start=1):
            if _TS_NOT_IMPLEMENTED_RE.search(line):
                hits.append(f"{rel_path}:{lineno}: unimplemented TS/JS error stub")

    assert not hits, "Unimplemented stubs or broad silent excepts detected:\n" + "\n".join(hits)


def test_guard_catches_unapproved_suppression(tmp_path: Path) -> None:
    sample = tmp_path / "sample.py"
    sample.write_text("x = 1  # noqa: F401\n", encoding="utf-8")
    hits = find_unapproved_suppressions(sample.read_text(encoding="utf-8"), "src/sample.py", {})
    assert hits == ["src/sample.py:1: unapproved suppression '# noqa'"]


def test_guard_catches_broad_silent_except_and_not_implemented() -> None:
    code = (
        "def f():\n"
        "    try:\n"
        "        raise NotImplementedError()\n"
        "    except Exception:\n"
        "        pass\n"
    )
    hits = find_python_stubs_and_silent_excepts(code, "src/sample.py")
    assert hits == [
        "src/sample.py:3: raise NotImplementedError",
        "src/sample.py:4: broad/bare silent except: pass",
    ]
