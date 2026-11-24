# TraceQ Web UI/UX Design Guide (`docs/DESIGN.md`)

Single source of truth for the visual system, information architecture, and regulated data-presentation rules of `web/` under [ADR 0014](adr/0014-web-ui-architecture-tailwind-v4-radix-and-design-system.md).

---

## 1. Design Philosophy & Non-Negotiables

- **Aesthetic direction:** *Precision Clinical Slate-Teal* — calm, high-contrast, light-theme-only enterprise workbench optimised for QA, Validation, and GMP review.
- **3-second orientation:** Every workspace screen immediately communicates: (1) current qualification stage, (2) active blockers (`Konflik`, `Celah`, open Deviations, undecided items), and (3) the single primary next action.
- **Hard domain boundaries:**
  - **100% self-hosted / offline:** Zero external CDNs; `@fontsource-variable/inter` bundled via `next/font/local`.
  - **AI is advisory only ([ADR 0002](adr/0002-ai-advisory-only.md), [ADR 0009](adr/0009-non-critical-human-in-the-loop-under-draft-annex-22.md)):** Proposals never auto-decide; human roles (`deciding`, `approving`, `executing`, `witnessing`, `read-only`) and Audit Trail integrity are preserved.
  - **WCAG 2.1 AA (≥ 4.5:1):** Colour is never the sole indicator of status; every status pill/badge pairs colour with an icon/shape and explicit Indonesian text label.

---

## 2. Token System & Surface Layering

Declared in `web/src/app/globals.css` inside `@theme` with `--color-*: initial` (plus explicit `white`, `black`, `transparent`, `current`). Arbitrary hex/rgb/oklch literals in `.tsx` or `.css` outside `@theme` are forbidden (`web/src/colour-literals.test.ts`).

### 2.1. Three-Tier Surface Layering
| Token | Value | Usage |
| :--- | :--- | :--- |
| `--color-canvas` | `#f4f6f8` | App background, sidebar rail, page backdrop |
| `--color-surface` | `#ffffff` | Primary cards, data tables, drawers, modals (`1px solid #d8e0e8`) |
| `--color-sunken` | `#edf1f5` | Evidence blocks, verbatim PDF quotes, audit metadata |
| `--color-border` | `#d8e0e8` | Hairline dividers and card/table borders |
| `--color-ink` | `#0f172a` | Primary text and headings |
| `--color-ink-muted` | `#475569` | Secondary labels, timestamps, metadata |

### 2.2. Brand, Accent, & Semantic Status Tokens
- **Primary Teal:** `--color-accent: #0f766e`, hover `--color-accent-hover: #115e59`, subtle tint `--color-accent-soft: #f0fdfa`.
- **Coverage Classes (6):** Distinct foreground/background/border token triples for `Terpenuhi`, `Sebagian`, `Celah`, `Konflik`, `Tidak berlaku`, and `Perlu tinjauan` (each paired with a leading shape/icon).
- **Execution & Deviation Statuses (Step 5b):**
  - Execution Result: `Pass` (emerald), `Fail` (crimson), `Ambiguous / Needs Confirmation` (amber, only when not `Fail`).
  - Deviation Status: `Open` (crimson/amber), `Submitted` (sky/slate), `Closed` (emerald/neutral).

### 2.3. Typography
- **Font family:** `--font-inter` (`@fontsource-variable/inter`) with system fallback `"Segoe UI", system-ui, sans-serif`.
- **Numeric discipline:** `font-variant-numeric: tabular-nums` is mandatory on all URS/step IDs (`URS-…`), measured values, tolerances, `k/n` counts, and timestamps.
- **Heading hierarchy:** Strict `h1` → `h2` → `h3` per screen (no skipped levels).

---

## 3. Information Architecture & Layout Shell

- **Route Groups (zero double header):**
  - `(home)` for `/` (Runs list) and `/signin`.
  - `(run)` with `web/src/app/(run)/runs/[runId]/layout.tsx` for full-viewport run workspaces without a nested `1440px` outer wrapper.
- **Deduplicated Server Fetching:** Per-endpoint `React.cache` fetchers (`fetchRun`, `fetchDecisionCounts`, `fetchProtocol`) shared between layout and pages. All mutations call `revalidatePath(\`/runs/\${runId}\`, "layout")` so sidebar counts update immediately.
- **Persistent Collapsible Left Sidebar:**
  - `240px` expanded on desktop; auto-collapses to a `56px` icon-rail when a right drawer opens at `1366px`; becomes a slide-over drawer at `<1024px` (`390px`).
  - **Alur Kualifikasi** (unnumbered so runs with `review_package == null` omit `Draf Protokol` cleanly without numeric gaps):
    - `Matriks & Triage` (`/runs/[runId]`) — undecided/changed coverage badge (`fetchDecisionCounts`)
    - `Temuan Pra-Tinjauan` (`/runs/[runId]/findings`) — undecided badge
    - `Draf Protokol` (`/runs/[runId]/draft`) — shown only when `run.review_package != null`
    - `Protokol IQ/OQ` (`/runs/[runId]/protocol`) — status badge (`Draft` / `Disetujui`)
    - `Eksekusi & Deviasi` — reserved Step 5b slot ([ADR 0013](adr/0013-execution-results-judged-by-code-deviations-opened-by-code.md))
  - **Audit & Diagnostik:** `Yang Tidak Dimasukkan` (`/left-out`) · `Hasil Evaluasi` (`/eval`).
- **Compact Sticky Context Bar (`48px`):** Equipment/run identity (`TP-201`), signed-in persona Radix `DropdownMenu` (displaying persona name + role badge, with actions *"Ganti persona"* → `/signin` and *"Keluar"*), and one primary next-action CTA (using a thin client `useSelectedLayoutSegment()` wrapper).

---

## 4. Screen Anatomy & Hybrid Interaction Patterns

| Screen | Pattern | Key Rules |
| :--- | :--- | :--- |
| **Daftar Run (`/`)** | Clean Data Table | **Unauthenticated-safe without N+1 API calls** (renders only `listRuns` fields: equipment name `TP-201` primary; `created`/`model`/`mode`/`run_id` secondary metadata; no per-run blocker/decision count fetches on `/`). |
| **Matriks (`/runs/[runId]`)** | Compact Scannable Table + Right Slide-Over Drawer (`560–640px`) | 4–5 columns (~56px/row → 8–10 rows above the fold at `1366×768`). URL `?selected=URS-...`, Prev/Next navigation, Required vs Observed side-by-side. |
| **Temuan (`/findings`)** | Grouped Master-Detail Split-Pane (Opsi B) | Separates *Temuan Pemeriksaan (Aturan Deterministik)* vs *Temuan AI (Saran)* and *Dokumen yang Tidak Ada*, with 1-click triage filters (`Belum diputuskan`, `Aturan`, `AI`) and right inspection/decision workspace. |
| **Draf (`/draft`)** | Compact Ordered Table + Slide-Over Drawer (Opsi A) | Preserves draft step order in a compact table, opens step inspection/decisions in a right slide-over drawer, and keeps the *"Temuan tentang seluruh dokumen"* section below. |
| **Protokol (`/protocol`)** | Compact Table + Slide-Over Drawer + Radix Tabs | Compact status header; destructive *"Tarik protokol"* inside a Radix Confirmation Dialog; Radix `Tabs` organizing *Baris Protokol*, *Checklist & Salinan Beku* (`FrozenCopy`, `ApprovalForms` for approver role e.g. Dewi), and *Nomor Terlewat & Batas* (`MissedNumbers`, ADR 0012 *"Batas yang diketahui"*). |
| **Eksekusi & Deviasi (Step 5b)** | Full-Width Execution Workbench + Wide Sheet (`720px+`) | Locked non-editable AC unit suffix; ALCOA server timestamps; multi-attempt history, versioned corrections + Reason for Change, multi-instrument calibration validation, hash-bound Witness badge, and 4-way SoD Deviation Investigation/CAPA/Closure. |
| **Audit (`/left-out`, `/eval`)** | Diagnostic Tables & Summary Cards | Shared tokens and typography; remove redundant heading/column duplication. |
| **System States (`loading.tsx`, `error.tsx`, `not-found.tsx`)** | Shared Semantic Recovery Screens | Loading skeletons, localised error boundaries with retry, and localised not-found recovery screens included in redesign scope using shared semantic tokens. |

---

## 5. Data Presentation & Mutation Ergonomics

- **Required vs Observed Comparison:** Displayed together in one structured unit (`Disyaratkan` | `Teramati` + stage without duplicated prefix such as `FAT FAT-M-02` | `Status`).
- **GMP-Safe `ambiguous` Precedence:** `result === "fail"` (red) **always** takes precedence over `observed_value.type === "ambiguous"`. Only when `result !== "fail"` and `ambiguous` is true does the UI render amber `warn` + warning icon + *"Perlu konfirmasi nilai (ambigu)"* consistently in both the table chip and drawer detail.
- **Inline PDF Citation Viewer:**
  - Triggering a citation runs a `HEAD` pre-check on `/api/runs/{runId}/documents/{docId}/{rev}`.
  - `application/pdf` on desktop (`≥768px`) opens an **`85vw` Modal** with the verbatim quote in the header, `<iframe key={docId+page} src="...#page=N">`, and *"Buka di tab baru"*.
  - `.xlsx`, non-PDF, or mobile (`<768px`) renders a download/open fallback card; `404`/`500` renders a localised error alert (never raw FastAPI JSON).
- **Drawer Form State (`useActionState`):** Forms in drawers/split panes use React 19 `useActionState` + `revalidatePath` with controlled/echoed values so `422`/`409` errors display inline without resetting typed `Reason for Change`. Forms are keyed by item/proposal ID and prompt a dirty-form guard before switching items.

---

## 6. Accessibility, Keyboard Ergonomics & Verification

- **Row triggers:** Use real `<button>` or `<Link>` elements inside the primary ID cell (never `<tr onClick>`), satisfying `jsx-a11y` with zero suppressions.
- **Escape & Dialog stacking:** Rely solely on Radix native `Esc` handling; never attach a competing global `Esc` listener.
- **Triage shortcuts (`J`/`K`):** Disabled whenever focus is inside `input`, `textarea`, `select`, `[contenteditable]`, `[role="listbox"|"menu"|"combobox"]`, or when `Ctrl`/`Cmd`/`Alt` is pressed.
- **Verification gates:** Every PR slice must pass `uv run pytest tests/test_boundaries.py -q`, `npm run typecheck`, `npm run lint`, `npm test` (using `css: false` and typed `jsdom` polyfills in `web/src/test/setup.ts`), `npm run build`, and visual/contrast checks at `390px`, `1366px`, and `1440px`.
