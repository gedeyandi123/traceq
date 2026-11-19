// Tests for heldout-bash.mjs. Usage: node .claude/hooks/heldout-bash.test.mjs
// Dummy command strings only: nothing here opens or names a real held-out file.
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { check } from "./heldout-bash.mjs";

const W = "bash scripts/heldout_run.sh";
const cases = [
  // [command, expect deny?]
  // Unrelated commands and the dev split pass.
  ["git status --short", false],
  ["uv run pytest -q tests/test_eval.py", false],
  ["uv run traceq run --equipment TP-201", false],
  ["ls fixtures/tp201", false],
  // tp2010 does not match tp[-_]?202 (it reads 201, then 0), so it passes.
  ["echo tp2010", false],
  // The plain wrapper call passes, also behind rtk or rtk proxy, and with quoted arguments.
  [`${W} PW-001 -- uv run traceq run --equipment PW-001`, false],
  [`${W} TP-202 -- uv run python -m traceq_eval score --equipment TP-202`, false],
  [`rtk ${W} TP-202 -- uv run traceq_eval TP-202`, false],
  [`rtk proxy ${W} PW-001 -- uv run traceq_eval PW-001`, false],
  [`bash ./scripts/heldout_run.sh PW-001 -- echo 'a | b; c > d'`, false],
  // Held-out names anywhere else are denied, in any case and spelling.
  ["cat data/TP-202/x.md", true],
  ["cat data/tp-202/x.md", true],
  ["grep -r TP_202 src", true],
  ["ls fixtures/tp202", true],
  ["head docs/PW-001.md", true],
  ["head docs/pw001.md", true],
  ["head docs/Pw_001.md", true],
  ["uv run traceq run --equipment PW-001", true],
  // The wrapper does not excuse a chain, pipe, redirection or substitution around it.
  [`${W} PW-001 -- echo x | cat`, true],
  [`${W} PW-001 -- echo x && cat runs/PW-001/out.log`, true],
  [`git status && ${W} PW-001 -- echo x`, true],
  [`${W} PW-001 -- echo x; cat y`, true],
  [`${W} PW-001 -- echo x || cat y`, true],
  [`${W} PW-001 -- echo x > out.txt`, true],
  [`${W} PW-001 -- echo x 2>&1`, true],
  [`${W} PW-001 -- echo $(cat y)`, true],
  [`${W} PW-001 -- echo "$(cat y)"`, true],
  [`${W} PW-001 -- echo \`cat y\``, true],
  [`${W} PW-001 -- echo x &`, true],
  [`${W} PW-001 -- echo x\ncat y`, true],
  [`FOO=1 ${W} PW-001 -- echo x`, true],
  [`sh scripts/heldout_run.sh PW-001 -- echo x`, true],
  [`bash scripts/other.sh PW-001 -- echo x`, true],
  [`bash -c "${W} PW-001 -- echo x"`, true],
].map(([cmd, deny]) => ["Bash", cmd, deny]);

// PowerShell has no wrapper exception: the wrapper is a bash script, run through the Bash tool.
const powershell = [
  ["Get-ChildItem fixtures/tp201", false],
  ["git status --short", false],
  ["Get-Content data/TP-202/x.md", true],
  ["Select-String -Path src -Pattern pw_001", true],
  [`${W} PW-001 -- echo x`, true],
  [`rtk proxy ${W} TP-202 -- echo x`, true],
].map(([cmd, deny]) => ["PowerShell", cmd, deny]);

// The hook entry point reads the tool name and command from the PreToolUse event on stdin.
function viaStdin(tool, cmd) {
  const event = JSON.stringify({ tool_name: tool, tool_input: { command: cmd } });
  const out = spawnSync(process.execPath, [fileURLToPath(new URL("./heldout-bash.mjs", import.meta.url))],
    { input: event, encoding: "utf8" }).stdout;
  return out ? JSON.parse(out).hookSpecificOutput.permissionDecisionReason : null;
}

let fail = 0;
let total = 0;
for (const [tool, cmd, expectDeny] of [...cases, ...powershell]) {
  const r = check(cmd, tool);
  const ok = Boolean(r) === expectDeny;
  total++;
  if (!ok) fail++;
  console.log(`${ok ? "ok  " : "FAIL"} ${expectDeny ? "deny" : "pass"}  ${tool}  ${JSON.stringify(cmd)}`);
}
for (const [tool, cmd, expectDeny] of [
  ["Bash", `${W} PW-001 -- echo x`, false],
  ["Bash", "cat data/TP-202/x.md", true],
  ["PowerShell", `${W} PW-001 -- echo x`, true],
  ["PowerShell", "git status", false],
]) {
  const r = viaStdin(tool, cmd);
  const ok = Boolean(r) === expectDeny && (!r || r.includes(tool === "PowerShell" ? "Use the Bash tool" : "heldout_run.sh"));
  total++;
  if (!ok) fail++;
  console.log(`${ok ? "ok  " : "FAIL"} ${expectDeny ? "deny" : "pass"}  ${tool} (stdin)  ${JSON.stringify(cmd)}`);
}
console.log(`\n${total - fail}/${total} passed`);
process.exit(fail ? 1 : 0);
