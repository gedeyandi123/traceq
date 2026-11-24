import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

import { colourLiterals, stripAllowedCssBlocks, tsxColourLiterals } from "./colour-literals";

// ADR 0014: no colour literals in `.css` or `.tsx` outside `@theme` in `globals.css`.

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

describe("tsxColourLiterals", () => {
  it.each([
    ["arbitrary hex bg", '<div className="bg-[#fff]" />', "bg-[#fff]"],
    ["arbitrary rgb text", '<span className="text-[rgb(15,23,42)]" />', "text-[rgb(15,23,42)]"],
    ["arbitrary oklch border", '<div className="border-[oklch(0.5_0.1_200)]" />', "border-[oklch(0.5_0.1_200)]"],
    ["arbitrary named colour", '<div className="bg-[red]" />', "bg-[red]"],
    ["inline style hex", '<div style={{ color: "#0f172a" }} />', "#0f172a"],
    ["inline style rgb", '<div style={{ backgroundColor: "rgb(0, 0, 0)" }} />', "rgb("],
    ["SVG hex fill", '<svg><rect fill="#ff0000" /></svg>', "#ff0000"],
    ["SVG named stroke", '<svg><path stroke="red" /></svg>', "red"],
  ])("flags %s", (_, tsx, literal) => {
    expect(tsxColourLiterals(tsx)).toEqual([literal]);
  });

  it.each([
    ["semantic Tailwind tokens", '<div className="bg-surface text-ink border-border" />'],
    ["arbitrary size classes", '<div className="w-[560px] text-[11px] backdrop-blur-[1px]" />'],
    ["SVG currentColor and none", '<svg><path fill="none" stroke="currentColor" /></svg>'],
    ["inline style width percentage", '<div style={{ width: `${pct}%` }} />'],
    ["inline style token", '<div style={{ color: "var(--color-ink)" }} />'],
  ])("passes %s", (_, tsx) => {
    expect(tsxColourLiterals(tsx)).toEqual([]);
  });
});

describe("every CSS and TSX file under src", () => {
  const src = import.meta.dirname;
  const allFiles = readdirSync(src, { recursive: true, encoding: "utf8" });
  const cssFiles = allFiles.filter((f) => f.endsWith(".css"));
  const tsxFiles = allFiles.filter((f) => f.endsWith(".tsx"));

  it("exists, so the guards are not vacuous", () => {
    expect(cssFiles.length).toBeGreaterThan(0);
    expect(tsxFiles.length).toBeGreaterThan(0);
  });

  it.each(cssFiles)("%s has no colour literal outside @theme", (file) => {
    const normalized = file.replace(/\\/g, "/");
    const isGlobalsCss = normalized === "app/globals.css";
    const raw = readFileSync(join(src, file), "utf8");
    const stripped = stripAllowedCssBlocks(raw, isGlobalsCss);
    expect(colourLiterals(stripped)).toEqual([]);
  });

  it.each(tsxFiles)("%s has no colour literal", (file) => {
    const raw = readFileSync(join(src, file), "utf8");
    expect(tsxColourLiterals(raw)).toEqual([]);
  });
});
