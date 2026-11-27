import { existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { expect, test } from "vitest";

import messages from "../../messages/id.json";

const SRC = resolve(__dirname, "..");
/** Namespaces the root layout forwards to the browser (the `clientMessages` object). */
function rootClientNamespaces(): string[] {
  const layout = readFileSync(join(SRC, "app", "layout.tsx"), "utf8");
  const block = /const clientMessages = \{([^}]*)\}/.exec(layout);
  expect(block).not.toBeNull();
  return [...(block?.[1] ?? "").matchAll(/(\w+):\s*allMessages\./g)].map((m) => m[1] ?? "");
}

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const p = join(dir, name);
    return statSync(p).isDirectory() ? walk(p) : [p];
  });
}

/** A module specifier to a file: `@/` from `src`, `./` and `../` from the importing file. */
function resolveImport(src: string, from: string, spec: string): string | null {
  let base: string;
  if (spec.startsWith("@/")) base = join(src, spec.slice(2));
  else if (spec.startsWith(".")) base = resolve(dirname(from), spec);
  else return null;
  for (const c of [
    base,
    `${base}.tsx`,
    `${base}.ts`,
    join(base, "index.tsx"),
    join(base, "index.ts"),
  ]) {
    if (existsSync(c) && statSync(c).isFile()) return c;
  }
  return null;
}

/** Every static `import`/`export ... from`, bare `import "x"` and `import("x")` specifier. */
function specifiers(text: string): string[] {
  const found = [
    ...text.matchAll(/\bfrom\s*["']([^"']+)["']/g),
    ...text.matchAll(/\bimport\s*["']([^"']+)["']/g),
    ...text.matchAll(/\bimport\(\s*["']([^"']+)["']\s*\)/g),
  ];
  return found.map((m) => m[1] ?? "");
}

/** Files reachable from the route files under `root` through `@/` and relative imports. */
function reachable(src: string, root: string): Set<string> {
  const seen = new Set<string>();
  const queue = walk(root).filter((f) => /\.tsx?$/.test(f) && !/\.test\./.test(f));
  while (queue.length > 0) {
    const file = queue.pop()!;
    if (seen.has(file)) continue;
    seen.add(file);
    for (const spec of specifiers(readFileSync(file, "utf8"))) {
      const next = resolveImport(src, file, spec);
      if (next && /\.tsx?$/.test(next)) queue.push(next);
    }
  }
  return seen;
}

/** `"use client"` as the file's directive: first statement, after comments and blank lines only. */
const USE_CLIENT = /^(?:\s|\/\/[^\n]*|\/\*[\s\S]*?\*\/)*["']use client["']/;

/** `"file: Namespace"` for every client component reachable from `root` using an unforwarded one. */
function unforwarded(src: string, root: string, forwarded: string[]): string[] {
  const missing: string[] = [];
  for (const file of reachable(src, root)) {
    const text = readFileSync(file, "utf8");
    if (!USE_CLIENT.test(text)) continue;
    for (const m of text.matchAll(/useTranslations\(\s*["']([A-Za-z]+)[."']/g)) {
      if (!forwarded.includes(m[1] ?? "")) {
        missing.push(`${file.slice(src.length + 1).replaceAll("\\", "/")}: ${m[1] ?? ""}`);
      }
    }
  }
  return missing;
}

test("every namespace a client component under (home) uses reaches the browser", () => {
  expect(unforwarded(SRC, join(SRC, "app", "(home)"), rootClientNamespaces())).toEqual([]);
});

test("every forwarded namespace exists in the messages", () => {
  for (const ns of rootClientNamespaces()) expect(messages).toHaveProperty(ns);
});

/** A throwaway `src` tree: `files` maps a path under it to its text. */
function tree(files: Record<string, string>): string {
  const src = mkdtempSync(join(tmpdir(), "client-ns-"));
  for (const [path, text] of Object.entries(files)) {
    const full = join(src, path);
    mkdirSync(dirname(full), { recursive: true });
    writeFileSync(full, text);
  }
  return src;
}

const client = (ns: string) =>
  `"use client";\nexport function C() { useTranslations("${ns}.x"); return null; }\n`;
const page = (spec: string) => `import { C } from "${spec}";\nexport default C;\n`;

test("the scan finds a client component reached through a relative import", () => {
  const src = tree({
    "app/(home)/page.tsx": page("./parts/Widget"),
    "app/(home)/parts/Widget.tsx": client("Hidden"),
  });
  expect(unforwarded(src, join(src, "app", "(home)"), [])).toEqual([
    "app/(home)/parts/Widget.tsx: Hidden",
  ]);
});

test("the scan follows a relative import up a directory", () => {
  const src = tree({
    "app/(home)/deep/page.tsx": page("../../../lib/Widget"),
    "lib/Widget.tsx": client("Hidden"),
  });
  expect(unforwarded(src, join(src, "app", "(home)"), [])).toEqual(["lib/Widget.tsx: Hidden"]);
});

test("the scan resolves an index.ts re-export to the client component behind it", () => {
  const src = tree({
    "app/(home)/page.tsx": page("@/components/widget"),
    "components/widget/index.ts": 'export { C } from "./Widget";\n',
    "components/widget/Widget.tsx": client("Hidden"),
  });
  expect(unforwarded(src, join(src, "app", "(home)"), [])).toEqual([
    "components/widget/Widget.tsx: Hidden",
  ]);
});

test("the scan follows a bare import and a dynamic import", () => {
  const src = tree({
    "app/(home)/page.tsx": 'import "@/a";\nconst B = () => import("@/b");\nexport default B;\n',
    "a.tsx": client("FromBare"),
    "b.tsx": client("FromDynamic"),
  });
  expect(unforwarded(src, join(src, "app", "(home)"), []).sort()).toEqual([
    "a.tsx: FromBare",
    "b.tsx: FromDynamic",
  ]);
});

test("a directive after a leading comment still marks a client component", () => {
  const src = tree({
    "app/(home)/page.tsx": page("@/W"),
    "W.tsx": `// header\n/* block */\n${client("Hidden")}`,
  });
  expect(unforwarded(src, join(src, "app", "(home)"), [])).toEqual(["W.tsx: Hidden"]);
});

test("the text 'use client' later in a file does not make it a client component", () => {
  const src = tree({
    "app/(home)/page.tsx": page("@/W"),
    "W.tsx":
      'import { useTranslations } from "next-intl";\n// "use client" is not the directive here\n' +
      'export function C() { useTranslations("Server.x"); return null; }\n',
  });
  expect(unforwarded(src, join(src, "app", "(home)"), [])).toEqual([]);
});

test("a forwarded namespace is not reported, and a file outside (home) is not scanned", () => {
  const src = tree({
    "app/(home)/page.tsx": page("./W"),
    "app/(home)/W.tsx": client("Shared"),
    "app/other/Unreached.tsx": client("Hidden"),
  });
  expect(unforwarded(src, join(src, "app", "(home)"), ["Shared"])).toEqual([]);
});
