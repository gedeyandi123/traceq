// PreToolUse hook for read-only subagents (the `reviewer` agent's frontmatter): Bash may run only
// commands that read. Every segment of a pipeline or `&&` chain must match the allowlist; output
// redirection, command substitution and anything not listed are denied.
// Tests: node .claude/hooks/readonly-bash.test.mjs
export function check(cmd) {
  if (/\$\(|`/.test(cmd)) return "command substitution is not allowed in a read-only agent.";
  const noSafeRedirects = cmd.replace(/\d?>\s*\/dev\/null|2>&1/g, "");
  if (/>/.test(noSafeRedirects)) return "output redirection is not allowed in a read-only agent.";
  for (const raw of cmd.split(/&&|\|\||[;|\n]/)) {
    const seg = raw.trim().replace(/^(\w+=\S*\s+)*/, "").replace(/^rtk\s+(proxy\s+)?/, "");
    if (!seg) continue;
    const reason = segment(seg.split(/\s+/));
    if (reason) return `${reason} (${seg})`;
  }
  return null;
}

const READ_TOOLS = new Set(["ls", "cat", "head", "tail", "wc", "grep", "rg", "sort", "uniq", "cut", "diff",
  "jq", "echo", "pwd", "which", "cd", "tr", "basename", "dirname", "stat", "file", "true", "test"]);
const GIT_READ = new Set(["diff", "log", "show", "status", "rev-parse", "blame", "merge-base", "ls-files",
  "grep", "shortlog", "describe", "cat-file", "rev-list", "name-rev"]);

function segment([cmd, ...args]) {
  if (READ_TOOLS.has(cmd)) return null;
  if (cmd === "sed") return args.some((a) => /^-[a-zA-Z]*i/.test(a) || a.startsWith("--in-place")) ? "sed -i writes files" : null;
  if (cmd === "find") return args.some((a) => /^-(delete|exec|execdir|ok|okdir|fprint|fprintf|fls)$/.test(a)) ? "find may only list" : null;
  if (cmd === "git") {
    const i = args.findIndex((a) => !a.startsWith("-") && args[args.indexOf(a) - 1] !== "-C");
    const sub = args[i];
    if (GIT_READ.has(sub)) return null;
    if (sub === "branch" && args.slice(i + 1).every((a) => /^(--list|-a|-r|-v|-vv|--show-current)$/.test(a))) return null;
    if (sub === "worktree" && args[i + 1] === "list") return null;
    return `git ${sub ?? ""} is not read-only`;
  }
  if (cmd === "gh") {
    const [sub, verb] = args;
    const ok = { pr: ["view", "diff", "checks", "list"], issue: ["view", "list"], repo: ["view"], run: ["view", "list"] };
    if (ok[sub]?.includes(verb)) return null;
    if (sub === "api" && !args.some((a) => /^(-X|--method|-f|-F|--field|--raw-field|--input)$/.test(a))) return null;
    return `gh ${sub ?? ""} ${verb ?? ""} is not read-only`;
  }
  if (cmd === "uv" && args[0] === "run" && /^(pytest|pyright)$/.test(args[1] ?? "")) return null;
  return `${cmd} is not on the read-only allowlist`;
}

if (/readonly-bash\.mjs$/.test(process.argv[1] ?? "")) {
  let input = "";
  for await (const chunk of process.stdin) input += chunk;
  let cmd = "";
  try { cmd = JSON.parse(input).tool_input?.command ?? ""; } catch { process.exit(0); }
  const reason = check(cmd);
  if (reason) {
    console.log(JSON.stringify({ hookSpecificOutput: { hookEventName: "PreToolUse", permissionDecision: "deny",
      permissionDecisionReason: `read-only agent: ${reason}` } }));
  }
}
