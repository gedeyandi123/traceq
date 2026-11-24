"""scripts/heldout_run.sh: held-out command output goes to a log, never to the terminal.

Dummy commands only: the wrapper is never run on held-out files here.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "heldout_run.sh"
MARKER = "MARKER-7f3a9c"


def _find_bash() -> str | None:
    if os.name == "nt":
        for candidate in (
            r"C:\Program Files\Git\bin\bash.exe",
            r"C:\Program Files\Git\usr\bin\bash.exe",
        ):
            if Path(candidate).is_file():
                return candidate
    found = shutil.which("bash")
    if found and os.name == "nt" and "system32" in found.lower():
        return None
    return found


BASH = _find_bash()

# Without bash the wrapper cannot run at all; CI (ubuntu) and Git Bash on Windows both have it.
pytestmark = pytest.mark.skipif(BASH is None, reason="bash is not installed")


def run(*args: str, script: Path = SCRIPT) -> subprocess.CompletedProcess[str]:
    assert BASH is not None
    return subprocess.run(
        [BASH, str(script), *args], capture_output=True, text=True, timeout=60, check=False
    )


def log_path(result: subprocess.CompletedProcess[str]) -> Path:
    line = next(x for x in result.stdout.splitlines() if x.startswith("log: "))
    raw = line.removeprefix("log: ")
    if os.name == "nt" and len(raw) >= 3 and raw[0] == "/" and raw[2] == "/":
        raw = f"{raw[1].upper()}:{raw[2:]}"
    return Path(raw)


def test_an_unknown_tag_is_refused() -> None:
    result = run("TP-201", "--", "echo", MARKER)
    assert result.returncode == 2
    assert MARKER not in result.stdout + result.stderr


def test_output_reaches_only_the_log() -> None:
    result = run("PW-001", "--", "bash", "-c", f"echo {MARKER}; echo {MARKER} >&2")
    log = log_path(result)
    try:
        assert result.returncode == 0
        assert MARKER not in result.stdout + result.stderr
        assert "exit: 0" in result.stdout
        assert log.parent == ROOT / "heldout-out" / "PW-001"
        assert log.read_text(encoding="utf-8").count(MARKER) == 2
    finally:
        log.unlink()


def test_the_exit_code_passes_through() -> None:
    result = run("TP-202", "--", "bash", "-c", f"echo {MARKER}; exit 7")
    log = log_path(result)
    try:
        assert result.returncode == 7
        assert "exit: 7" in result.stdout
        assert MARKER not in result.stdout + result.stderr
    finally:
        log.unlink()


def test_a_repo_outside_the_main_checkout_is_refused(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    # A worktree placed beside the temp repo is outside that repo's main checkout.
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-q", "--allow-empty", "-m", "x"],
        check=True,
        env=_git_identity(),
    )
    other = tmp_path.parent / f"{tmp_path.name}-wt"
    subprocess.run(["git", "-C", str(tmp_path), "worktree", "add", "-q", str(other)], check=True)
    (other / "scripts").mkdir()
    shutil.copy(SCRIPT, other / "scripts" / "heldout_run.sh")
    try:
        result = run("PW-001", "--", "echo", MARKER, script=other / "scripts" / "heldout_run.sh")
        assert result.returncode == 2
        assert MARKER not in result.stdout + result.stderr
        assert not (other / "heldout-out").exists()
    finally:
        shutil.rmtree(other, ignore_errors=True)


def _git_identity() -> dict[str, str]:
    return {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.invalid",
    }
