# UI redesign: discovery, baseline audit, design direction (prototype branch)

Status: draft on the throwaway branch `feat/ui-redesign-prototype`, 17 Nov 2026. It feeds the redesign spec; the owner decides what moves to `main`. Labels: **[F]** repository fact, **[O]** observed in the browser, **[A]** design assessment, **[R]** recommendation, **[?]** unknown or assumption.

Screenshots: headless Chrome over the DevTools protocol, production build of `main` (port 3000), signed in as Ayu (deciding role), run `20261116T173605Z-249deb` (r7 replay). Viewports: 1366x768, 125% zoom (CSS 1093x614, DPR 1.25) and phone 390x844.

## 0. Discovery

| Area | Fact |
|---|---|
| Stack [F] | Next.js 16.4.6 (App Router, Turbopack), React 19.3.1, TypeScript 5.9.3 `strict` + `noUncheckedIndexedAccess`, next-intl 4.15.1 (one locale, `id`), openapi-fetch 0.17.0 over generated types. No UI library, no icon library, no chart library, no form library, no Tailwind. |
| Rendering [F] | Every page is a Server Component with `dynamic = "force-dynamic"`. Zero client components in production code. Decisions are Server Actions (`decisions/actions.ts`) posting HTML forms; errors come back as `?error=`. |
| Styling [F] | One `globals.css` (122 lines): element selectors (`header`, `main`, `table.matrix`), hand-picked hex colours, `system-ui` font, no tokens, no focus styles, no breakpoints. Only the matrix and tally tables are styled; findings, left-out and eval tables are browser defaults. |
| Routes [F] | `/` run list · `/signin` personas · `/runs/[id]` matrix · `/runs/[id]/findings` · `/runs/[id]/left-out` · `/runs/[id]/eval`. No shared run layout; each page draws its own back link and partial link row. |
| Tests [F] | Vitest + Testing Library, 14 tests in 5 files. They assert text, roles (`columnheader "Cakupan"`, `region` names, buttons "Terima"/"Tolak", `textbox` required inside the form), `data-testid` (row ids, eval metrics) and the absence of password inputs. They do not assert classes or layout. No E2E, no visual or a11y tooling. CI: typecheck, test, build; generated API types checked against the API. |
| Behaviour that must not move [F] | Form fields and hidden inputs of each decision; `required` on reason; which buttons each access mode shows; `?error=` banners; citation links (`/api/runs/.../documents/...#page=n`, new tab, quote in `title`); read-only reasons; URL structure. |
| Unknowns [?] | Projector resolution and colour rendering at the session; whether the demo laptop has internet when `npm run build` runs (matters for web fonts); eval page empty in this capture because the eval API on 8001 had no scored run loaded (expected K13 state, not a defect). |

## 1. Baseline audit (prioritised)

Severity: S1 hurts the demo story or a decision, S2 slows scanning, S3 polish.

| # | Finding | Evidence | Why it matters | Sev | Scope |
|---|---|---|---|---|---|
| 1 | **No visual system at all.** Default blue/purple visited links, default grey buttons, browser table defaults on 3 of 4 data pages, `system-ui` at one size. | [O] every screenshot; [F] `globals.css` | Reads as an unfinished internal tool; the audience judges trust in the analysis partly by this. | S1 | systemic |
| 2 | **No run-level navigation.** Matrix links to findings, left-out and eval in a sentence; findings links only to left-out; left-out and eval link back only to the matrix. No "where am I". | [O] headers of the four run pages | The demo story (section 4 of the runbook) walks matrix → findings → left-out → eval; the presenter hunts for links. | S1 | systemic |
| 3 | **Matrix is 7,644 px tall at 1366 (8,528 at 125%), about 10 screens for 38 rows.** Every row carries a full decision panel (button, select, textarea, button) and every evidence step in full. | [O] `runs_RUN-1366.png`; [F] `MatrixTable.tsx`, `Decisions.tsx` | The decision forms, not the data, set the row height. Hard to scan for Konflik/Celah. | S1 | matrix |
| 4 | **The decision tally is an 8-column table for 1–2 rows of numbers**, with the longest header ("Diputuskan sebelumnya, tidak diusulkan run ini") setting its width. | [O] matrix, findings | The one number that matters in the demo (Belum diputuskan 38 → 37) is buried. | S2 | matrix, findings |
| 5 | **Header wraps to two lines**: brand, tagline and session are inline, the sign-out form is a block. No brand mark, no favicon, every tab titled "TraceQ". | [O] all; [F] `layout.tsx`, no `icon` file | Weak "where am I"; tabs indistinguishable when PDFs open in new tabs. | S2 | systemic |
| 6 | **Horizontal overflow**: left-out is 1,193 px wide at 125% (and on phone) because `<pre>` blocks of unquoted URS text do not wrap; matrix (810 px) and findings (759 px) overflow on phone. | [O] `scrollWidth` per viewport | 125% on the projector is the main demo setting; left-out scrolls sideways there. | S1 | left-out; S3 phone |
| 7 | **Findings tables are unstyled and misaligned**: headers centred, cells vertically centred while citation lists and decision panels are top-aligned, no row separation. | [O] `runs_RUN_findings-1366.png` | Hard to tell which decision belongs to which finding. | S2 | findings |
| 8 | **Inputs look broken**: textarea placeholder in the browser's monospace font, buttons stretched full-width in a narrow column, no focus ring beyond the browser default. | [O] matrix, findings | Primary action (Terima) and secondary (Ubah kelas, Tolak) look identical; weak keyboard visibility. | S2 | systemic |
| 9 | **Data typography**: IDs, values and k/n are proportional figures; values like `20–70 rpm` and `120.000 tablet/h` do not align; evidence repeats the stage ("FAT FAT-M-01"). | [O] matrix | Scanning numbers is the core task of a matrix. | S2 | matrix, eval |
| 10 | **Empty and unavailable states are plain sentences** (eval not scored, run list empty, personas unavailable). | [O] eval | Fine functionally; looks like an error in a demo. | S3 | eval, list, signin |
| 11 | **Run list and sign-in are bare bullet lists**; the run id link is the only clickable thing, metadata is a sentence. | [O] home, signin | First screen of the demo. | S2 | list, signin |
| 12 | Colour carries meaning only with a text label next to it (coverage pills say "Celah"), contrast of `#666` on white is 5.7:1. | [F] `globals.css` | Already acceptable; keep labels when restyling. | — | — |

What I would **not** change [A]: the server-only architecture (no client JS needed for any of this), the HTML-form decision flow, next-intl strings, the table as the matrix's primary form (see section 3).

## 2. Design direction [R]

**Personality: a precise QA document, not a SaaS dashboard.** The users review vendor evidence against a URS and sign decisions into an audit trail. The interface should feel like a well-set controlled document: calm neutrals, one ink colour for actions and navigation, semantic colour only for Coverage classes and pass/fail, numbers in tabular figures, dense but with clear rhythm. No gradients, no decorative illustrations, shadows only to lift the sticky header and menus.

| Token group | Proposal |
|---|---|
| Neutrals | Slate scale: canvas `#f6f7f9`, surface `#ffffff`, subtle `#eef1f5`, border `#d8dde4`, text `#16202c`, secondary `#4a5868`, muted `#6b7785` (≥ 4.5:1 on white). |
| Ink (primary) | Deep navy `#1d3f6e`, hover `#16325a`, soft `#e6edf7`. Used for the app bar, active tab, primary button, focus ring. |
| Semantic | Coverage: Dicakup vendor green, Sebagian amber, Hanya di lokasi blue-grey, Celah red, Konflik solid red, Belum dinilai grey; each pill keeps its text and gets a leading shape (●, ◐, ○, ▲, ◆) so meaning never rests on colour alone. Pass green, fail red, warning amber, info blue. |
| Type | System stack (`"Segoe UI Variable", "Segoe UI", system-ui, sans-serif`) or a bundled Inter via `next/font/local` (owner decision, see section 4). Scale 12 / 13 / 14 (body, data) / 16 / 20 / 24 px; weights 400 / 600 / 700; `font-variant-numeric: tabular-nums` for IDs, values, counts, k/n; document IDs in a medium weight, not monospace. |
| Space | 4 px base: 4, 8, 12, 16, 24, 32, 48. Page gutter 24 px desktop, 16 px phone. |
| Shape | Radius 4 (inputs, pills 999), 8 (panels). Borders 1 px; one shadow level for sticky/overlay. |
| Motion | 120 ms colour transitions on hover/focus only; none under `prefers-reduced-motion`. |
| Theme | Light only. A dark theme adds cost with no demand: projector and document review favour light. |

Structure:

- **App bar** (one line): TraceQ wordmark, tagline in muted text, session at the right with a quiet "Keluar".
- **Run header** (new `app/runs/[runId]/layout.tsx`): breadcrumb "Semua run / TP-201", run id and mode as metadata, and **tabs** Matriks · Temuan pra-tinjauan · Yang tidak dimasukkan · Hasil evaluasi, the current one marked with `aria-current="page"`. Same URLs, same links, just always present. (Layouts do not get `searchParams`, which is fine: tabs need only the run id.)
- **Summary strip** replacing the tally table: counts per Coverage class and "Diputuskan k/n" as compact stat chips. The full tally stays available (same numbers) in a disclosure, so no information is lost.
- **Matrix stays a table** (tests need `columnheader "Cakupan"` and the per-row `data-testid`), restyled: sticky header, coloured left edge per class, tabular values, evidence folded to one summary line per row with the full list in a `<details>` (text stays in the DOM, so tests and find-in-page still work).
- **Decision cell**: state first, "Terima" as the primary button, "Ubah kelas"/"Tolak" with its select and reason inside a disclosure. This is the one interaction change (one extra click to change a class); see decision 3.
- **Findings and left-out**: same table component and styles as the matrix; left-out `<pre>` wraps.
- **Run list and sign-in**: run list as a table with equipment, model, mode, created; sign-in as persona cards with the role as a label.

Round 1 prototype verdict: structure B (triage) and C (board) cannot hold the "zero test edits" guard, because the matrix tests look for the table's column header. A (table) is the structure that fits the guard; round 2 changes the visual system, which round 1 did not touch (the global shell, type and controls stayed raw, which is most of why it did not look better).

## 3. Implementation strategy [R]

1. Prototype round 2 on this branch: tokens + shell + run layout, applied to **all six pages**, two token sets switchable (the switcher swaps a class on `<body>`; same components) so the owner picks a palette on real data.
2. Owner picks; verdict recorded here and on the spec issue.
3. Spec: CSS Modules + tokens, no behaviour change, zero test edits, checks at 1366x768, 125% and phone; runbook cases re-run.
4. Reviewer doubt pass; owner approves; tickets in order: tokens and app shell → run layout and tabs → shared table and decision cell → matrix → findings → left-out, eval, list, sign-in.

## 4. Decisions for the owner

1. **Scope**: all six pages (recommended: the problems are systemic) or the matrix only.
2. **Typeface**: system Segoe UI (zero risk, no network at build) or bundled Inter via `next/font/local` (more distinctive; adds an OFL font file of roughly 100–350 KB, depending on subset, to the repo; no network at build or run time).
3. **Decision cell**: fold "Ubah kelas"/"Tolak" behind a disclosure (rows about half as tall; one extra click, runbook K4/K5/K6/K8 steps gain "buka") or keep every form open as now.
4. **Timing vs the 25 Nov freeze**: redesign lands after the freeze release (recommended: the runbook was rehearsed on today's UI) or before it.
