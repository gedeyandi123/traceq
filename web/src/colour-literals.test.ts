import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

import { colourLiterals } from "./colour-literals";

// ADR 0011: a CSS Module uses only tokens, never a colour value.

describe("colourLiterals", () => {
  it.each([
    ["a hex colour", ".a { color: #fff; }", "#fff"],
    ["a long hex colour", ".a { background: #0b5d63 }", "#0b5d63"],
    ["rgb()", ".a { box-shadow: 0 1px 2px rgb(16 24 40 / 0.06); }", "rgb("],
    ["hsl()", ".a { color: hsla(0, 0%, 0%, 0.5); }", "hsla("],
    ["oklch()", ".a { color: oklch(0.5 0.1 200); }", "oklch("],
    ["a named colour", ".a:hover { color: white; }", "white"],
    ["a named colour in a shorthand", ".a { border: 1px solid Red; }", "red"],
    ["a colour in a custom property", ".a { --edge: #ccc; }", "#ccc"],
  ])("flags %s", (_, css, literal) => {
    expect(colourLiterals(css)).toEqual([literal]);
  });

  it.each([
    ["white-space: nowrap", ".a { white-space: nowrap; }"],
    ["a token", ".a { color: var(--color-text); }"],
    ["a token whose name holds a colour word", ".a { color: var(--cov-red-fg); }"],
    ["color-mix() over tokens", ".a { border-color: color-mix(in srgb, var(--color-ink) 35%, transparent); }"],
    ["transparent and currentColor", ".a { background: transparent; border-color: currentColor; }"],
    ["a selector with a pseudo-class", ".a:hover, .b:focus-visible { outline-offset: 2px; }"],
    ["a breakpoint", "@media (max-width: 640px) { .a { display: none; } }"],
    ["a comment that names a colour", "/* white text on #000 */ .a { display: block; }"],
    ["a font family", ".a { font-family: \"Segoe UI\", system-ui, sans-serif; }"],
    ["an id-like class in a value", ".a { grid-area: tan-area; }"],
  ])("passes %s", (_, css) => {
    expect(colourLiterals(css)).toEqual([]);
  });
});

describe("every CSS Module under src", () => {
  const src = import.meta.dirname;
  const modules = readdirSync(src, { recursive: true, encoding: "utf8" }).filter((f) => f.endsWith(".module.css"));

  it("exists, so the guard is not vacuous", () => {
    expect(modules.length).toBeGreaterThan(0);
  });

  it.each(modules)("%s has no colour literal", (file) => {
    expect(colourLiterals(readFileSync(join(src, file), "utf8"))).toEqual([]);
  });
});
