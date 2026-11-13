// Tests for readonly-bash.mjs. Usage: node .claude/hooks/readonly-bash.test.mjs
import { check } from "./readonly-bash.mjs";

const cases = [
  // [command, expect deny?]
  ["git diff main...HEAD", false],
  ["git log main..HEAD --oneline", false],
  ["git -C E:/traceq show HEAD:CLAUDE.md", false],
  ["git branch --show-current", false],
  ["git worktree list", false],
  ["gh pr diff 25", false],
  ["gh issue view 12 --json title,body,comments", false],
  ["gh api repos/o/r/issues/5", false],
  ["uv run pytest -q tests/test_eval.py", false],
  ["uv run pyright", false],
  ["grep -rn answer_key src | head -20", false],
  ["git diff main...HEAD 2>&1 | wc -l", false],
  ["cd E:/traceq && git status --short", false],
  ["sed -n 1,40p CLAUDE.md", false],
  ["find src -name '*.py'", false],
  ["rtk git log -3", false],
  ["git commit -am x", true],
  ["git push origin feat/x", true],
  ["git checkout main", true],
  ["git reset --hard HEAD~1", true],
  ["git branch -D feat/x", true],
  ["gh pr merge 25 --squash", true],
  ["gh pr comment 25 --body hi", true],
  ["gh issue close 12", true],
  ["gh api -X POST repos/o/r/issues -f title=x", true],
  ["echo x > CLAUDE.md", true],
  ["cat a >> b", true],
  ["sed -i s/a/b/ CLAUDE.md", true],
  ["find . -name '*.pyc' -delete", true],
  ["rm -rf src", true],
  ["python -c 'open(\"x\",\"w\")'", true],
  ["uv run python scripts/x.py", true],
  ["uv add requests", true],
  ["echo $(rm x)", true],
  ["git status; rm x", true],
  ["tee out.txt", true],
];

let fail = 0;
for (const [cmd, expectDeny] of cases) {
  const r = check(cmd);
  const ok = Boolean(r) === expectDeny;
  if (!ok) fail++;
  console.log(`${ok ? "ok  " : "FAIL"} ${expectDeny ? "deny" : "pass"}  ${cmd}${r ? `  -> ${r}` : ""}`);
}
console.log(`\n${cases.length - fail}/${cases.length} passed`);
process.exit(fail ? 1 : 0);
