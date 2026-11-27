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
| `--color-input-border` | `#7a899c` | WCAG 1.4.11 (≥ 3:1) borders on form inputs, selects, and textareas (`FormControls.tsx`) |
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
  - `(home)` for `/` (Runs list), `/equipment` (Equipment Registry), `/equipment/[equipment]/upload` (Draft upload, Step 6 epic #375), and `/signin` with shared header navigation (`Daftar Run` / `Daftar Equipment`).
  - `(run)` with `web/src/app/(run)/runs/[runId]/layout.tsx` for full-viewport run workspaces without a nested `1440px` outer wrapper.
- **Deduplicated Server Fetching:** Per-endpoint `React.cache` fetchers (`fetchRun`, `fetchDecisionCounts`, `fetchRounds`, `fetchProtocol`, `fetchExecution`, `fetchQualificationReport`, `fetchEquipmentList`) shared between layout and pages. All mutations call `revalidatePath(\`/runs/\${runId}\`, "layout")` so sidebar counts update immediately.
- **Persistent Collapsible Left Sidebar:**
  - `240px` expanded on desktop; auto-collapses to a `56px` icon-rail when a right drawer opens at `1366px`; becomes a slide-over drawer at `<1024px` (`390px`).
  - **Alur Kualifikasi** (unnumbered so runs with `review_package == null` omit `Draf Protokol` cleanly without numeric gaps):
    - `Matriks & Triage` (`/runs/[runId]`) — undecided/changed coverage badge (`fetchDecisionCounts`)
    - `Temuan Pra-Tinjauan` (`/runs/[runId]/findings`) — undecided badge
    - `Draf Protokol` (`/runs/[runId]/draft`) — shown only when `run.review_package != null`
    - `Dokumen & Ronde` (`/runs/[runId]/rounds`) — current round badge (`R1`/`R2` + status)
    - `Protokol IQ/OQ` (`/runs/[runId]/protocol`) — status badge (`Draft` / `Disetujui`)
    - `Eksekusi & Deviasi` (`/runs/[runId]/execution`) — status badge (`Sedang berjalan` / `Selesai`) & open Deviation count ([ADR 0013](adr/0013-execution-results-judged-by-code-deviations-opened-by-code.md))
    - `Laporan Kualifikasi` (`/runs/[runId]/report`) — Qualification Report preview, approver issue form & immutable PDF exports (Step 7)
  - **Audit & Diagnostik:** `Yang Tidak Dimasukkan` (`/left-out`) · `Hasil Evaluasi` (`/eval`).
- **Compact Sticky Context Bar (`48px`):** Breadcrumb (`Semua run / Daftar Equipment / TP-201`), signed-in persona `SessionMenu` (`lib/persona.ts`, supporting `EXECUTING_ROLE` alongside deciding/approving/witnessing/read-only), and one primary next-action CTA (including *"Buka Eksekusi & Deviasi"* when `protocolStatus === "approved"` and *"Buka Laporan Kualifikasi"* when `executionStatus === "completed"`).
- **Shared Primitives & A11y:** `FormControls` (`FieldInput`/`FieldTextarea`/`FieldSelect` without `focus:outline-none`), `CopyHashButton` (`aria-live="polite"`), `Alert`, `RouteErrorView`, `Drawer` (`size="md" | "wide"` up to `760px` with `onCloseAutoFocus` focus restoration), `useTriageKeyboardNav` (`J`/`K`), lazy-mounted `PdfCitationModal`, `ElectronicSignatureDialog` (owned Radix `Dialog` for Step 8 signing), `SignatureBadge`, and `@media (prefers-reduced-motion: reduce)` support.

---

## 4. Screen Anatomy & Hybrid Interaction Patterns

| Screen | Pattern | Key Rules |
| :--- | :--- | :--- |
| **Daftar Run (`/`)** | Clean Data Table | **Unauthenticated-safe without N+1 API calls** (renders only `listRuns` fields: equipment name `TP-201` primary; `created`/`model`/`mode`/`run_id` secondary metadata; no per-run blocker/decision count fetches on `/`). |
| **Matriks (`/runs/[runId]`)** | Compact Scannable Table + Right Slide-Over Drawer (`560–640px`) | 4–5 columns (~56px/row → 8–10 rows above the fold at `1366×768`). URL `?selected=URS-...`, Prev/Next navigation, Required vs Observed side-by-side. |
| **Temuan (`/findings`)** | Grouped Master-Detail Split-Pane (Opsi B) | Separates *Temuan Pemeriksaan (Aturan Deterministik)* vs *Temuan AI (Saran)* and *Dokumen yang Tidak Ada*, with 1-click triage filters (`Belum diputuskan`, `Aturan`, `AI`) and right inspection/decision workspace. |
| **Draf (`/draft`)** | Compact Ordered Table + Slide-Over Drawer (Opsi A) | Preserves draft step order in a compact table, opens step inspection/decisions in a right slide-over drawer, and keeps the *"Temuan tentang seluruh dokumen"* section below. |
| **Unggah Draf (`/equipment/[equipment]/upload`, epic #375)** | Notice + Upload Form + Job Table | Reached from the *"Unggah draf"* link of the Equipment Registry; needs the deciding role for that Equipment. Always-visible warn `Alert` *"Hanya data sintetis"* (Mode Cloud sends text to an external provider, ADR 0001) above one file input (`FormControls`, PDF only, limits line *"Maksimal {mb} MB dan {pages} halaman"*) and a primary *"Unggah"* `Button` (Lucide `Upload`, label becomes *"Mengunggah…"* while busy). Rejections show a `fail` `Alert` (`role="alert"`, inside an `aria-live="polite"` region) with the localised reason (not a PDF or over the page cap, too large, budget, role, session). **States:** *empty* (`EmptyState` *"Belum ada unggahan"*, also when the page is reached with no jobs); *processing* (job row pill `Antre` info / `Berjalan` warn, polled every 2 s, `Rev n`, hash prefix, page count, and *"diputar ulang dari rekaman, tanpa biaya langsung"* when no live budget is held); *failed* (`Gagal` fail pill and the job's own message in the result cell); *done* (`Selesai` pass pill with *"Buka draf"* and *"Buka ronde tinjauan"* links). Page-level states: signed out (info `Alert` with sign-in link), forbidden, *"Unggahan tidak aktif"* (server without uploads), unavailable. Pill text always accompanies colour. Rev 0 is the first upload; each later one is the next revision. |
| **Dokumen & Ronde (`/rounds`, Step 6)** | Tabbed Workbench + Radix Tabs & Modal | 3 tabs (*Versi Dokumen*, *Ronde Tinjauan & Diff*, *Ekspor Laporan*); cross-round diff summary with a per-finding state list *Temuan yang perlu dilihat dulu* (text label only, no colour dependence): *Selesai* (resolved), *Bertahan, berubah* (persisted-but-changed) and *Baru* (new) are listed, while unchanged *Bertahan* findings appear in the counts only; decisions are counted *Terbawa*, *Terbuka ulang / berubah* or *Belum diputuskan*; a re-uploaded revision shows as *Revisi baru*, never as removed; Radix Confirmation Modal *"Tutup ronde"* (`returned_for_revision` requires Reason for Change, ADR 0007 notice, `useActionState` + dirty-form guard); auth-forwarding PDF download (`/api/rounds/{roundId}/exports/{exportId}/pdf`). |
| **Protokol (`/protocol`)** | Compact Table + Slide-Over Drawer + Radix Tabs | Non-sticky submission checklist; destructive *"Tarik protokol"* and permanent *"Setujui protokol"* (showing hash prefix & ADR 0007 notice) inside Radix Confirmation Modals; Radix `Tabs` organizing *Baris protokol*, *Checklist & salinan beku* (`FrozenCopy`, `ApprovalForms`), and *Nomor terlewat & batas*. |
| **Protokol dari draf (`/protocol`, epic #375)** | Same screen, extra panels | *"Mulai protokol dari draf yang ditinjau"* starts a Protocol pinned to a draft revision. A source panel (*"Sumber: draf protokol"*: document, rev, hash) states the pin; when a newer revision exists a warning says the Protocol does not follow it and to return or withdraw. Tab *Langkah draf* lists draft steps the citation check dropped or that map to zero or several requirements as *"Belum dapat dipakai"* until mapped to exactly one requirement or rejected. Each row carries a *Sumber* chip (*Draf*, *Rancangan TraceQ*, *Ditulis orang*), the step and Acceptance Criterion decisions, findings about its requirement, an IQ/OQ Stage selector and, for an accepted finding on an unchanged row, a required written reason. The blocker list names every open item (undecided finding, missing reason, missing Stage, unresolved step). The frozen copy panel (*"Sumber dan keputusan draf (salinan versi 2)"*) lists the source, dropped and mapped steps, every finding with decision, author and reason. A Protocol pinned to a revision older than the latest is refused at approval and at submit (HTTP 409, ADR 0012 of 27 November 2026) with an inline `Alert` *"Tidak ditandatangani: protokol ini terpaku pada revisi draf yang lebih lama …"* (return if submitted, withdraw, then start again from the latest revision). The same refusal holds while a newer revision of that Equipment's upload is still queued or running and not yet registered; the 409 and the *Alert* are the same, and a failed upload does not count. A stale read on a Protocol pinned to the latest revision renders *"Tidak ditandatangani: revisi draf yang lebih baru masuk …"*; both keep typed input and are told apart by the API's `X-TraceQ-Conflict` code, not its words. Nobody who uploaded the draft revision the Protocol is pinned to, and nobody who registered it by an import, may approve it (409, code `uploader_approves`; ADR 0012 of 27 November 2026, extended to the importer on 28 November 2026): the approval dialog closes and an inline `Alert` *"Tidak disetujui: Anda yang mengunggah atau mengimpor revisi draf …"* asks for another Approver. |
| **Eksekusi & Deviasi (Step 5b)** | Tabbed Workbench + `FilterBar` + Wide Drawer (`760px`) | Radix `Tabs` (*Baris eksekusi*, *Deviasi*, *Riwayat & salinan*), 1-click `FilterBar` (*Semua*, *Belum dicatat*, *Lulus*, *Gagal*, *Menunggu Saksi*, *Referensi vendor*), stage & `witness_required` badges, `unconfirmed_witness_rows` completion blocker, compact table + `ExecutionRowDrawer` (`size="wide"`) with `version_hash` prefix, dirty-form guards on all 3 execution drawers, and Confirmation Modals for *"Tutup deviasi"* and *"Selesaikan eksekusi"*. |
| **Laporan Kualifikasi (`/report`, Step 7)** | Summary + Export Workbench | Technical conclusion badge (`qualified` / `qualified_with_deviations` / `not_qualified`), per-stage counts (`IQ`, `OQ`, `IQ/OQ (Belum Dipisah)`, `Referensi Vendor`), Test Steps & Retest lineage, Deviations & Witnessing summary, ADR 0007 signature notice titled *"Tanda tangan (ADR 0007)"* (the hedge sentence before any export, the backend label of the latest export afterwards), approver issue form (`next_requalification_date` hidden when `not_qualified`), immutable export history with `CopyHashButton` & auth-forwarding PDF download (`/api/executions/{executionId}/qualification-reports/{exportId}/pdf`). |
| **Daftar Equipment (`/equipment`, Step 7)** | Lifecycle Registry Table | Authenticated (`401` → signed-out `Alert` + `/signin` CTA); renders Equipment with latest Round, Protocol, Execution (+ open deviations), Qualification Report conclusion & direct links using each nested summary's own `run_id`, and `next_requalification_date` (fallback `"Belum dijadwalkan"`). |
| **Masuk (`/signin`, Step 8)** | Dual-Mode Identity Screen | Demo mode renders passwordless persona cards (`identitas demo`, no password field). OIDC mode (`TRACEQ_OIDC_CLIENT_ID` set) renders the Keycloak Authorization Code + PKCE CTA (`/api/auth/login`), keeping `traceq_token` and `traceq_id_token` in `httpOnly`, `sameSite=lax` cookies. |
| **Electronic Signature UX (Step 8)** | `ElectronicSignatureDialog` + `SignatureBadge` | Applied across all 5 signing surfaces: Protocol Submission (`prepared`), Protocol Approval (`approved`), Deviation Closure (`approved`), Witness Confirmation (`witnessed`, including `voided`), and Qualification Report Approval (`approved`). The badge pill is neutral (never green) for a verified signature: a matching hash is not an approval; only failure (red), void and demo use a tone. Displays target summary, `content_hash` preview, `Signature Meaning`, and honest ADR 0007 dynamic label (Demo vs Keycloak OIDC vs pre-Step-8 recorded status). OIDC mode triggers `GET /api/auth/reauth` (`prompt=login&max_age=0&login_hint`), preserves Qualification Report form state (`conclusion_note`, `next_requalification_date`) in `sessionStorage` across redirect, re-opens the dialog with a live 60s countdown from `auth_time`, requires explicit 1-click confirmation (no auto-submit), and surfaces `reauth_required` distinctly from `unauthorized`. |
| **Audit (`/left-out`, `/eval`)** | Diagnostic Tables & Summary Cards | Shared tokens and typography; remove redundant heading/column duplication. |
| **System States (`loading.tsx`, `error.tsx`, `not-found.tsx`)** | Shared Semantic Recovery Screens | Loading skeletons, localised error boundaries with retry, and localised not-found recovery screens included in redesign scope using shared semantic tokens. |

---

## 4a. Evidence Labels (epic #375)

- **"dev only" (*"Hanya pengembangan"*):** `warn` pill (`border-warn-edge bg-warn-soft text-warn`) on the draft-to-Protocol surfaces and in the Pre-review report; every figure about the loop is k/n on synthetic data.
- **"not reviewed by a practitioner" (*"Belum ditinjau praktisi"*):** `warn` pill beside every finding of `ac_outside_documented_capability`, `unit_error` and `outdated_reference` (draft table, drawer, Protocol row findings); the report carries it in English.
- **"Awaiting the practitioner's answer (#245)" (*"Menunggu jawaban praktisi (#245)"*):** `info` pill on the Protocol-from-draft start panel.
- Labels are text pills, never colour alone, use only the semantic tokens of section 2 (no literals, `web/src/colour-literals.test.ts`), and stay light-only, self-hosted and offline (ADR 0014): no CDN, no dark mode. They never claim time or review rounds saved, and never the word "compliant".
- **Signature check:** the badge writes *"Hash cocok"* with a `ShieldCheck` icon in a neutral tone (`text-ink-muted`), never green and never "Terverifikasi": a matching hash says the stored data is unchanged, not that anyone approved it. A failed check keeps `fail` red; "not checked" stays neutral text.

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
- **Verification gates:** Every PR slice must pass `scripts/verify.ps1 -Mode fast` (+ `npm run build` when `web/` changes, using `css: false` and typed `jsdom` polyfills in `web/src/test/setup.ts`). Run 1 visual/contrast checkpoint at `390px`, `1366px`, and `1440px` per UI epic before opening the final PR to `main`.
