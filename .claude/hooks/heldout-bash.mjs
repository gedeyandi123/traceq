// PreToolUse hook for Bash and PowerShell (registered in .claude/settings.json, so it covers the main
// session and every subagent): denies any command that names a held-out item (TP-202, PW-001; case-insensitive
// `tp[-_]?202` or `pw[-_]?0`), because its output would put held-out text in the agent's context.
// The one exception is a single call of the output-capturing wrapper,
//   bash scripts/heldout_run.sh <TAG> -- <command...>   (optionally after `rtk` or `rtk proxy`)
// with no pipe, `;`, `&&`, `||`, `&`, redirection, subshell, newline or command substitution outside
// single or double quotes, and no substitution inside double quotes. A PowerShell command that names a
// held-out item is always denied: the wrapper is a bash script, so it runs through the Bash tool.
// This is an alarm against accidents, not a security boundary: a determined command can name a file
// without its name (globs, variables, other scripts). Read/Edit are covered by the file-name deny
// rules in .claude/settings.local.json; this covers Bash.
// `pw[-_]?0` is broad on purpose (it also catches pw0, pw-002, ...); `tp2010` does not match.
// Tests: node .claude/hooks/heldout-bash.test.mjs
const HELDOUT = /tp[-_]?202|pw[-_]?0/i;
const WRAPPER = /^(.*\/)?scripts\/heldout_run\.sh$/;

export function check(cmd, tool = "Bash") {
  if (!HELDOUT.test(cmd)) return null;
  if (tool !== "Bash") {
    return `the ${tool} command names a held-out item (TP-202 or PW-001). Use the Bash tool with a single `
      + "call of `bash scripts/heldout_run.sh <TP-202|PW-001> -- <command...>`, which writes the output to "
      + "heldout-out/<TAG>/ and prints only the exit code and the log path.";
  }
  const tokens = wrapperTokens(cmd);
  if (tokens) {
    const words = tokens[0] === "rtk" ? tokens.slice(tokens[1] === "proxy" ? 2 : 1) : tokens;
    if (words[0] === "bash" && WRAPPER.test(words[1] ?? "")) return null;
  }
  return "the command names a held-out item (TP-202 or PW-001). Run it as a single call of "
    + "`bash scripts/heldout_run.sh <TP-202|PW-001> -- <command...>`, which writes the output to "
    + "heldout-out/<TAG>/ and prints only the exit code and the log path.";
}

// Splits a command into words, or returns null when it holds shell syntax outside quotes that
// could chain, redirect or substitute (so it is not a single plain command).
function wrapperTokens(cmd) {
  const tokens = [];
  let word = null;
  let quote = null;
  for (let i = 0; i < cmd.length; i++) {
    const c = cmd[i];
    if (quote === "'") {
      if (c === "'") quote = null; else word += c;
      continue;
    }
    if (quote === '"') {
      if (c === "`" || (c === "$" && cmd[i + 1] === "(")) return null;
      if (c === '"') quote = null; else word += c;
      continue;
    }
    if (c === " " || c === "\t") {
      if (word !== null) tokens.push(word);
      word = null;
      continue;
    }
    if (/[|;&<>()`\n\r\\]/.test(c) || (c === "$" && cmd[i + 1] === "(")) return null;
    if (c === "'" || c === '"') quote = c;
    else word = (word ?? "") + c;
    if (word === null) word = "";
  }
  if (quote) return null;
  if (word !== null) tokens.push(word);
  return tokens;
}

if (/heldout-bash\.mjs$/.test(process.argv[1] ?? "")) {
  let input = "";
  for await (const chunk of process.stdin) input += chunk;
  let cmd = "";
  let tool = "Bash";
  try {
    const event = JSON.parse(input);
    cmd = event.tool_input?.command ?? "";
    tool = event.tool_name ?? "Bash";
  } catch { process.exit(0); }
  const reason = check(cmd, tool);
  if (reason) {
    console.log(JSON.stringify({ hookSpecificOutput: { hookEventName: "PreToolUse", permissionDecision: "deny",
      permissionDecisionReason: `held-out alarm: ${reason}` } }));
  }
}
