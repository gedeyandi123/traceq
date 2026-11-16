# Web styling: CSS Modules over design tokens, no UI library, bundled Inter, light theme only

Decided 17 November 2026, after the UI redesign prototype (throwaway branch `feat/ui-redesign-prototype`, e54cf7e; never merged). Before the prototype, `web/` had one `globals.css` with element selectors and hand-picked hex values, no tokens and no focus styles; three of the four data pages used browser table defaults. The audit found the problem was the missing visual system, not the page structure, so this ADR fixes how the web app is styled. The redesign spec builds on it.

**Tokens.** Every colour, font size, space, radius, shadow, control height and duration is a CSS custom property on `:root` in `web/src/app/globals.css`. That file also holds the base element rules (body, headings, links, focus ring) and nothing component-specific. The palette is the Teal one the owner picked in prototype round 2. The six Coverage classes each have their own foreground, background and edge tokens. A class always carries its text label and a leading shape, so colour is never the only sign of its meaning.

**Components.** Each component's styles live in a CSS Module next to it (`Component.module.css`). The module uses only tokens. A colour value is never written in a module: no `#…`, `rgb()`, `hsl()` or named colour other than `transparent` and `currentColor`. A Vitest test reads every `*.module.css` under `web/src` and fails on a colour literal in a declaration value (values only, so a property such as `white-space: nowrap` never matches), so the rule holds without a new linter. Font sizes and spacing come from the token scale by convention; no test enforces that. Breakpoints are plain `@media` queries in the modules. Custom properties cannot be used in media queries, so there are exactly three widths, written as numbers and listed in a comment in `globals.css`: `max-width: 640px` (phone), `900px` (the app bar stacks), `1199px` (wide tables fold). A new width needs a reason in that comment.

**No new runtime and no client JavaScript for styling.** No Tailwind, no component library (shadcn/ui, Radix, MUI, Chakra) and no CSS-in-JS. Every page is a Server Component today, and styling never makes one a client component; a later feature that needs client JavaScript decides that in its own spec. Disclosures (folded forms, evidence lists, unquoted URS text) use native `<details>`/`<summary>`, so styling adds no client component and the text stays in the DOM for tests and find-in-page.

**Typeface.** Inter (OFL-1.1) comes from the pinned npm package `@fontsource-variable/inter` (5.3.0), Latin subset (`inter-latin-wght-normal.woff2`, about 48 KB). It loads through `next/font/local` and is exposed as `--font-inter`, behind the fallback stack `"Segoe UI", system-ui, sans-serif`. The font file is part of the build output, so neither `npm run build` nor the running app requests a font host; the demo laptop may be offline. A version bump of the package is an ordinary dependency change and is checked by `npm run build`.

**Light theme only.** No dark theme and no `prefers-color-scheme` rules. Nobody has asked for one, and document review and a projector both favour light. A dark theme would double every contrast check. It can be added later as a second set of token values without touching the modules.

**Tests do not assert styling.** Render tests keep asserting roles, accessible names, text and `data-testid`, never class names or layout. A restyle therefore edits no existing test, and that is the guard against behaviour sneaking into a restyle.

## Consequences

- A visual change is usually a token change in one file. A new component brings its own module and reuses the tokens.
- No CSS Module writes a colour value; the colour-literal test enforces this. Colours in TSX (for example an inline SVG) use `currentColor` or a token by convention.
- Contrast is checked per token pair once, in the browser, and reported in the PR that changes a token. A background derived with `color-mix()` is checked on the rendered page, not as a token pair.
- The font file is a build input; its path in `node_modules` is a dependency on the package layout, so `npm ci` must run before `npm run build` (already true for every build).

## Considered Options

- **Tailwind CSS:** rejected. The tokens would live in one place in either approach. Tailwind adds a build dependency and a second styling vocabulary in every JSX line, and the diffs of a restyle would mix markup with styling. CSS Modules ship with Next.js and need nothing new.
- **A component library (shadcn/ui on Radix, MUI, Chakra):** rejected. Its interactive parts are client components; the app has none and needs none (forms are HTML forms posting to Server Actions). MUI and Chakra also bring runtime CSS-in-JS, and the result looks like every other admin tool.
- **CSS-in-JS (styled-components, Emotion):** rejected. It needs client components or extra server setup in the App Router, for no gain over CSS Modules.
- **System font only (Segoe UI / `system-ui`):** zero risk, but the owner preferred Inter's look on the projector. Inter is bundled, so it carries no network risk either; the system stack stays as the fallback.
- **Inter from Google Fonts (`next/font/google`):** rejected. It downloads the font at build time, which fails on an offline demo laptop.
- **Light and dark themes:** rejected for now, see above.
