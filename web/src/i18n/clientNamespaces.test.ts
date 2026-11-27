import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join, resolve } from "node:path";
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

const HOME = join(SRC, "app", "(home)");

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const p = join(dir, name);
    return statSync(p).isDirectory() ? walk(p) : [p];
  });
}

function resolveImport(spec: string): string | null {
  const base = join(SRC, spec.replace(/^@\//, ""));
  for (const c of [`${base}.tsx`, `${base}.ts`, join(base, "index.tsx")]) {
    if (existsSync(c)) return c;
  }
  return null;
}

/** Files reachable from the (home) route files through `@/` imports. */
function reachable(): Set<string> {
  const seen = new Set<string>();
  const queue = walk(HOME).filter((f) => /\.tsx?$/.test(f) && !/\.test\./.test(f));
  while (queue.length > 0) {
    const file = queue.pop()!;
    if (seen.has(file)) continue;
    seen.add(file);
    const text = readFileSync(file, "utf8");
    for (const m of text.matchAll(/from "(@\/[^"]+)"/g)) {
      const next = resolveImport(m[1] ?? "");
      if (next) queue.push(next);
    }
  }
  return seen;
}

test("every namespace a client component under (home) uses reaches the browser", () => {
  const forwarded = rootClientNamespaces();
  const missing: string[] = [];
  for (const file of reachable()) {
    const text = readFileSync(file, "utf8");
    if (!/^\s*["']use client["']/.test(text)) continue;
    for (const m of text.matchAll(/useTranslations\("([A-Za-z]+)[."]/g)) {
      if (!forwarded.includes(m[1] ?? "")) {
        missing.push(`${file.slice(SRC.length + 1)}: ${m[1] ?? ""}`);
      }
    }
  }
  expect(missing).toEqual([]);
});

test("every forwarded namespace exists in the messages", () => {
  for (const ns of rootClientNamespaces()) expect(messages).toHaveProperty(ns);
});
