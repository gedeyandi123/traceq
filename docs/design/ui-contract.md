# UI Contract — TraceQ Web (`web/`)

Complements [ADR 0011](file:///E:/traceq/docs/adr/0011-web-styling-css-modules-over-tokens.md) as the day-to-day UI contract for Phase A/B polish and Step 5b (ADR 0013).

## 1. Visual Personality & Tokens
- **Tone:** Enterprise clinical/GMP controlled document — calm crisp cool-neutral slate (`#f4f6f8` canvas, `#ffffff` surface) with Teal ink (`#0b5d63`), light theme only.
- **Typography:** Bundled Inter (`--font-inter`) via `next/font/local`. Use `font-variant-numeric: tabular-nums` (`cell.num` / `.meta dd`) for IDs, values, counts, and `k/n`.
- **Token SSOT:** All colours, type scale, spacing (4 px base), radii, shadows, and motion live in `:root` of `web/src/app/globals.css`.
- **Zero Colour Literals:** CSS Modules (`*.module.css`) NEVER write `#hex`, `rgb()`, `hsl()`, `oklch()`, or named colours (except `transparent` and `currentColor`), enforced by `web/src/colour-literals.test.ts`.
- **Breakpoints:** Only `640px` (phone), `900px` (app bar stacks), and `1199px` (wide tables fold / overview stacks).

## 2. Shared Primitives (`web/src/components/ui/`)
Reuse these primitives before creating one-off patterns:
- `CoveragePill` — coverage class badge with leading shape + text label (never colour alone).
- `Button` — variants: `primary` (one main CTA), `soft` (repeated row action), `quiet` (secondary), `danger` (destructive/withdraw/return).
- `StatusBadge` — semantic pill (`neutral | info | pass | warn | fail`) for protocol/execution states.
- `Alert` — structured callout (`info | warn | fail | pass`) with leading icon and `role="alert"` or `"status"`.
- `ProgressBar` — accessible `role="progressbar"` for decision/execution completion.
- `Disclosure` — native `<details>`/`<summary>` wrapper (text stays in DOM for tests & find-in-page).
- `Panel`, `SummaryLinks`, `SectionHeading`, `ModeBadge`, `EmptyState`, `DataTable` (`cell.num`, `cell.id`).

## 3. Inline SVG Icons (`web/src/components/ui/icons.tsx`)
- Zero external icon packages. All icons are inline SVGs (`16x16`, `stroke="currentColor"`, `aria-hidden="true"`) in `icons.tsx`, safe under CSP `img-src 'self'`.
- Never hardcode hex/rgb colours inside SVG props; inherit via `currentColor` or CSS tokens.

## 4. Server-First + Thin `"use client"` Islands
- **Default:** Every page (`page.tsx`) and data view stays a Server Component (`dynamic = "force-dynamic"`). Data fetching and Server Actions stay on the server.
- **Permitted `"use client"` islands (Phase B & Step 5b):** Only thin leaf components for genuine interactive ergonomics that HTML/CSS cannot do cleanly:
  1. Conditional form fields (e.g., `<AcShapeFields />` showing inputs for the selected `ac_type`).
  2. Pending submit feedback (`<SubmitButton />` using `useFormStatus`).
  3. Route error boundaries (`error.tsx`).
- **Forbidden:** Client-side data fetching libraries, global state stores, CSS-in-JS, Tailwind, or external UI kits.

## 5. Testing & Accessibility Guardrails
- Tests assert roles, accessible names, text, and `data-testid` — never CSS class names or layout.
- Semantic colour is always paired with text or shape. Interactive controls keep `:focus-visible` outlines.
