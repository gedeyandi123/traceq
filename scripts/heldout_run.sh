#!/usr/bin/env bash
# Runs a held-out command without its output reaching the terminal (and so the agent's context).
#
#   bash scripts/heldout_run.sh <TP-202|PW-001> -- <command...>
#
# stdout and stderr go to heldout-out/<TAG>/<UTC timestamp>.log under the repo root (git-ignored);
# the wrapper prints only the exit code and the log path, and exits with the command's exit code.
# The Bash alarm hook (.claude/hooks/heldout-bash.mjs) lets a held-out command through only as a
# single call of this script. The file-name deny rules that keep the logs out of Read cover only
# paths inside the main checkout, so the script refuses to run (exit 2) from a repo outside it.
set -u

usage() {
  echo "usage: bash scripts/heldout_run.sh <TP-202|PW-001> -- <command...>" >&2
  exit 2
}

[ $# -ge 3 ] || usage
tag=$1
case "$tag" in
  TP-202 | PW-001) ;;
  *) echo "heldout_run: unknown tag (expected TP-202 or PW-001)" >&2; exit 2 ;;
esac
[ "$2" = "--" ] || usage
shift 2

here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
root=$(git -C "$here" rev-parse --show-toplevel 2>/dev/null) || {
  echo "heldout_run: not inside a git repository" >&2
  exit 2
}
main=$(git -C "$root" worktree list --porcelain 2>/dev/null | sed -n '1s/^worktree //p')
root_abs=$(cd "$root" && pwd -P)
main_abs=$(cd "$main" 2>/dev/null && pwd -P) || main_abs=""
inside=0
# An empty main path would make the prefix "/" and match everything, so it counts as outside.
if [ -n "$main_abs" ]; then
  case "$root_abs/" in "$main_abs"/*) inside=1 ;; esac
fi
if [ "$inside" -ne 1 ]; then
  echo "heldout_run: this repo is outside the main checkout; the deny rules do not cover it" >&2
  exit 2
fi

dir="$root/heldout-out/$tag"
mkdir -p "$dir"
stamp=$(date -u +%Y%m%dT%H%M%SZ)
log="$dir/$stamp.log"
n=1
while [ -e "$log" ]; do
  log="$dir/$stamp-$n.log"
  n=$((n + 1))
done

"$@" >"$log" 2>&1 </dev/null
rc=$?
echo "exit: $rc"
echo "log: $log"
exit "$rc"
