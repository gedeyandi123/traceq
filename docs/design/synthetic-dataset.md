# Synthetic dataset design (v0)

Status: design for v0. Items marked **[D]** are parameters that a practising qualification supervisor (design partner) will confirm during discovery; v0 ships with the defaults stated here. Domain terms are defined in [`GLOSSARY.md`](../../GLOSSARY.md).

## 1. Purpose

One dataset serves four consumers. A document or defect that none of them needs is not created.

| Consumer | What it needs from the dataset |
|---|---|
| Demo story "a new tablet press arrives" | A realistic document package for new Equipment: URS, Vendor Documents, FAT, SAT |
| Evals (a product feature and the regression suite) | An answer key: extracted values, correct citations, documents that should exist, Coverage class per requirement |
| Pre-review | Planted defects, plus clean documents to measure false positives |
| Equipment Registry and Requalification | Qualification history for several items, with due dates overdue, due soon, and far off |

## 2. Principles

1. **World data first, documents second.** The fictional world is structured data (YAML validated by Pydantic). Documents are rendered from it, and the answer key is derived from the same data, so the two cannot drift apart.
2. **Defects are planted explicitly.** Each defect has an ID in the defect manifest, a location, and the expected finding. There are no accidental defects.
3. **Clean documents are required:** at least 30% of documents carry no defect, so Pre-review is measured on precision as well as recall.
4. **Reproducible.** Generation is deterministic from a seed. Binary output is never committed (section 8).
5. **Every value has a public source.** Each Acceptance Criterion and technical limit in the world data records its source in one of two tiers:
   - **Quoted:** regulation (CPOB / PerBPOM 7/2024, WHO TRS 1033 Annex 3, Permenaker), pharmacopoeia (Farmakope Indonesia), or literature (peer-reviewed papers, textbooks, brand-free trade press). The source stores `url`, a verbatim `quote` (≤ 200 characters) containing the value, and the `accessed` date.
   - **Site decision:** a URS value is the plant's own need, not a copy of a brochure. It stores a written `rationale`, who drafted it (`drafted_by`), and, where one exists, a quote from literature showing the value is realistic. A quote from a single study (e.g. the station count of the press it used) shows a value is realistic, not that a plant needs it, so such values are site decisions with a supporting quote, not quoted values.

   Real vendor brochures are not cited: the denylist keeps real vendor names out of the repository (principle 6), and literature plus practitioner review give the same evidence of realism.
6. **Everything is fictional:** plant, vendors, people, serial numbers. Vendor names are checked against registered trademarks before they are frozen, and a denylist check in CI blocks real equipment vendor names.
7. **No LLM-chosen number is frozen without human review.** For TP-201 and PW-001, a quoted value is copied from a cited source (principle 5): an LLM may do the copying, the schema checks that the value appears in its quote, and `scripts/verify_quotes.py` checks the quote against the live page. A site decision is a judgement; when an LLM drafts it (`drafted_by: llm`) it blocks freeze until a human signs it off (`reviewed_by: owner | practitioner`). Human review therefore goes to judged values, not to quotes the machine already checked. Other Equipment may be drafted with an LLM, then edited and frozen.

## 3. Regulatory references

CPOB (PerBPOM 7/2024) is the primary reference for every defect type and Coverage rule; EU GMP Annex 15 (2015), PIC/S, and WHO are cited as equivalents. Exceptions: water systems cite WHO TRS 1033 Annex 3, and good documentation practice (GDP) detail cites PIC/S PI 041-1 §8.7–8.8.

| Source | Used for |
|---|---|
| PerBPOM 7/2024, Ch. 10 (documentation), Ch. 12 (qualification and validation), Annex 7 (computerised systems) | Primary reference. PerBPOM 7/2025 only amends Annex 1. |
| EU GMP Annex 15 (2015) | Equivalent for qualification rules |
| WHO TRS 1033 Annex 3 §11.3 | Purified water: phased PQ, no production use during Phase 1 |
| PIC/S PI 041-1 §8.7–8.8 | GDP corrections |
| USP <1231> | Guidance for internal alert/action levels |

## 4. The fictional world

- **Plant:** one oral solid dose (OSD) site, one production building.
- **Governing documents:** a short Validation Master Plan (VMP) and a qualification SOP. Together they set the rules Pre-review checks: Requalification intervals per Equipment category, who signs what, document numbering, GDP correction rules, which Test Steps need a Witness, and the internal alert/action levels for water.
- **People:** 6–8 fictional people mapped to personas (Qualification Engineer, Qualification Supervisor, QA Approver, Production/Engineering Witness, System Admin). The same people are the demo accounts in the identity provider. Some defects use this mapping, e.g. performer = Witness.
- **Languages:** documents mix Indonesian and English **[D: proportion]**. Number and date formats follow the document language (Indonesian `0,5`, `1.000`, `dd/mm/yyyy`; English vendor documents `0.5`, `12-Mar-2026`, or ISO 8601). The answer key stores normalised values.

### Equipment

| Tag | Equipment | Depth | State at T0 | Role |
|---|---|---|---|---|
| TP-201 | Tablet press (new) | Hero, full package | SAT done, IQ/OQ not started | Main story: Traceability → gaps → drafted Test Steps |
| HSMG-101 | High-shear mixer granulator | Full history | Qualified; Requalification due T0+30d | Due soon in the registry |
| FBD-101 | Fluid bed dryer | Full history | Qualified; Requalification overdue T0−20d | Overdue; SAT report missing (missing-document recall) |
| CP-301 | Coating pan | Partial history | Qualified; open Change Control (motor replacement) | Requalification triggered by change |
| PW-001 | Purified Water System | Phased PQ | PQ Phase 3, month 7 | Long-running monitoring; outdated reference in a superseded protocol |
| TP-202 | Tablet press, different vendor | Hero, full package | SAT done | **Held-out eval split only**; never shown in the demo |
| (~20 items) | Balances, sieves, metal detector, deduster, … | Registry rows only | Mixed | Makes the registry look like a real plant |

**[D]** The Equipment list is confirmed against the types most often qualified in practice. The data model is generic: HVAC can be added later with data only.

### Dates

Dates are stored as offsets from T0 (`T0-400d`). Two corpus instances are rendered from the same data and seed:

- **Eval corpus:** fixed T0, frozen. Eval scores are comparable across runs.
- **Demo corpus:** re-rendered on every demo reset with T0 = reset day, so documents and the database agree. The registry always has overdue and due-soon items without editing data.

Registry state and history are seeded from world data; only the TP-201 package is extracted live in the demo. A virtual clock was rejected because the Audit Trail must record real time.

## 5. Document catalogue

### TP-201 package (hero)

| Document | Language | Format | Origin | Used for |
|---|---|---|---|---|
| URS / SKP, rev 0 and rev 1 (35–40 numbered requirements) | ID | Born-digital PDF | User | Starting point for Traceability; extraction eval; superseded revision with one changed value |
| Risk assessment (short FMEA) | ID | XLSX | User/QA | Marks Critical Aspects |
| Technical specification / datasheet | EN | PDF, dense tables | Vendor | Table extraction; conflicts with the URS |
| Functional design specification | EN | PDF | Vendor | Coverage of functions and interlocks (clean) |
| Material certificates 3.1 (product-contact parts) | EN | Scan | Vendor | OCR; one material conflict |
| Calibration certificates | EN | Scan | Vendor/lab | OCR; one expired certificate |
| FAT protocol and report | EN | PDF | Vendor | Vendor Evidence, Coverage |
| SAT report | EN/ID mixed | Scan, handwritten entries, stamps | Vendor + user | Hard OCR, Coverage, GDP defects |
| DQ report | ID | PDF | User | URS ↔ design link (clean) |

The TP-201 URS includes 4–6 data integrity requirements for the HMI (CPOB Annex 7: access levels, audit trail, alarm log, recipe backup, time synchronisation). Full computerised system validation is out of scope.

There is no IQ/OQ for TP-201: that is what the AI drafts. Its answer key is the list of expected gaps (section 6).

### TP-202 package (held out)

Same document types, different vendor and layout. The URS is prose and unnumbered tables; the answer key stores the requirement segmentation and scoring uses tolerant span matching.

### Equipment with history (HSMG-101, FBD-101, CP-301)

URS, approved IQ/OQ/PQ Protocols, Execution records, Qualification Reports, Deviations, Change Controls, and Requalification history. Format mix follows plant practice **[D: Word / Excel / paper / DMS]**.

### PW-001 (purified water)

At T0 the system is in **Phase 3, month 7**: Phases 1–2 complete, two quarterly trending points, the 12-month clock running. The corpus contains Protocol rev 1 (cites the outdated WHO TRS 970) and its replacement rev 2.

Monitoring data is LIMS-style, per sampling point and parameter, with an Indonesian seasonal pattern (feed-water bioburden rises in the rainy season). Planted events: one excursion handled correctly, one not followed up, and one use of water for production during Phase 1 (not allowed by TRS 1033 §11.3).

Specification values come from Farmakope Indonesia VI and supplements (verified against the official PDF when v2 is written; fallback USP <645>/<643>). Microbial alert/action levels are internal limits set in the VMP (USP <1231> guidance), not pharmacopoeial specifications. Evaluation against levels is done by deterministic rules.

## 6. Answer key

The answer key lives beside the world data and is never sent to an LLM.

### Requirements and Coverage

```yaml
- id: URS-TP201-014
  text: "Kecepatan turret dapat diatur pada rentang 10–80 rpm"
  source: {doc: URS-TP201, rev: 1, page: 4, section: "4.2"}
  param: turret_speed
  value: {min: 10, max: 80, unit: rpm}
  critical: true
  evidence:
    - {doc: FAT-TP201, section: "7.3", step: "FAT-7.3.2", result: passed, range_tested: {min: 10, max: 80}}
  expected_coverage: covered_by_vendor
  also_valid: []
```

Coverage classes:

| Class | Meaning | Example |
|---|---|---|
| `covered_by_vendor` | Vendor Evidence fully proves the requirement (decision table below) | Full speed range tested at an approved FAT |
| `partial` | Vendor tested it, but not enough; retest in OQ | FAT tested 10–60 rpm only |
| `site_only` | Cannot be tested by the vendor | Utility connections, performance in the production room |
| `gap` | No Evidence at all | Door interlock not mentioned in FAT/SAT |
| `conflict` | The design or delivered item does not meet the URS | URS requires SS 316L; the material certificate says 304 |

`conflict` (the thing does not meet the URS) is distinct from inconsistent data (two records state the same fact differently, e.g. SAT serial number ≠ nameplate). Each fact gets one primary label; an acceptable second label is recorded in `also_valid`.

Target distribution for TP-201: about 40% covered, 20% partial, 15% site_only, 20% gap, 5% conflict. **[D]** If vendor FAT/SAT is rarely reused in practice, the proportions stay and the framing becomes "this is what could be saved".

#### Decision table: `covered_by_vendor`

All four conditions must hold. The first failing condition decides the class (tie-break order top to bottom).

| # | Condition | Reference | If it fails |
|---|---|---|---|
| 1 | The vendor has been assessed and the requirement is within the assessed scope | CPOB Ch. 12 | `partial` if tested, else `gap` |
| 2 | The FAT/SAT protocol was approved by the site before execution | CPOB 12.14 | `partial` |
| 3 | The full URS range was tested | — | `partial` |
| 4 | The function is not affected by transport/installation (`transport_sensitive: false`), or it was retested at SAT | CPOB 12.24 | `partial` |

Vendor assessment state: TP-201 vendor assessed, full scope. TP-202 vendor assessed with limited scope (mechanical yes, control system/software no).

### Documents that should exist

Per Equipment and Qualification Stage, the VMP implies a list of required documents. The answer key stores that list and the documents deliberately left out (e.g. the FBD-101 SAT report, one HSMG-101 OQ attachment).

### Defect manifest

```yaml
- id: D-PW001-003
  type: outdated_reference
  doc: {id: OQP-PW001, rev: 1}
  location: {page: 3, section: "2. Referensi"}
  detail: "Cites WHO TRS 970 Annex 2; current is TRS 1033 Annex 3"
  severity: major
  layer: llm
  reference: {primary: "WHO TRS 1033 Annex 3"}
```

### Ambiguous values

Some values are deliberately ambiguous (`1.500 rpm` in a mixed-language document, `03/04/2026`). The expected answer is "ask for confirmation". Deterministic rules never score an ambiguous date.

### OCR locations

For scanned documents the renderer knows where each string was drawn, so the answer key stores bounding boxes. OCR accuracy is measured without manual annotation.

## 7. Planted defects

### Layers

Pre-review runs deterministic rules first and the LLM on the rest. A **Check Finding** (rule, no model trace) is kept separate from an **AI Finding**. Evals report per layer, which shows what actually needs AI.

### Taxonomy

Weights per type are set once discovery confirms which review errors are most common **[D]**.

| Type | Example | Layer | Reference |
|---|---|---|---|
| Missing signature/date | "Checked by" empty | Rule | CPOB Ch. 10 |
| Impossible date order | Execution before Protocol approval | Rule | CPOB Ch. 12 |
| Segregation of duties | Performer = Witness | Rule | SOP |
| Out-of-limit result marked pass | 85 rpm, limit 10–80, "Pass" | Rule | CPOB 12.16 |
| Failed result not raised as Deviation | Result outside AC, no Deviation | Rule | CPOB 12.16 |
| AC changed during Execution without Deviation | Protocol ±5%, executed against ±10% | Rule + LLM | CPOB 12.15 |
| Vendor protocol not approved by site | FAT executed without site approval | Rule | CPOB 12.14 |
| Expired test instrument calibration | Certificate expired before Execution | Rule | CPOB Ch. 12 |
| Calculation error | Wrong thermocouple average | Rule | — |
| Water used for production in Phase 1 | Batch record during Phase 1 | Rule | WHO TRS 1033 §11.3 |
| Referenced attachment missing | "See Attachment 4" | Rule + LLM | CPOB Ch. 10 |
| Outdated reference | WHO TRS 970 for water | LLM | — |
| Inconsistent data across documents | IQ serial ≠ nameplate | LLM | — |
| AC deviates from URS | Protocol ±10%, URS ±5% | LLM | — |
| GDP correction, three variants (overwrite without initials/date, missing reason, obliterated original) | Scanned SAT entry | LLM/vision | PIC/S PI 041-1 §8.7, CPOB 10.8 |
| Leftover from another Equipment **[D]** | Another tag left in a copied protocol | LLM | — |

Density: 1–3 defects per defective document; at least 30% of documents clean.

A vendor FAT/SAT whose own Acceptance Criterion tests less than the URS asks (e.g. 20–60 rpm against a URS of 20–70) is not "AC deviates from URS": that type applies to the site's own protocols. The shortfall is scored as Coverage `partial` (decision table condition 3), not as a defect.

### v0 scenarios (TP-201 package)

1. A SAT entry overwritten without initials/date (CPOB 10.8).
2. The tachometer calibration certificate expired on the SAT date.
3. SAT serial number ≠ nameplate/datasheet.
4. FAT protocol executed without site approval (CPOB 12.14).
5. A FAT result outside the AC marked "Pass".
6. Material certificate says 304; URS requires 316L (`conflict`).
7. `1.500 rpm` ambiguous.
8. URS rev 0 → rev 1 with one value changed.

The DQ report and functional specification are clean. About 10% of eval items are hallucination probes.

### World-data workflow

World data is filled in stages. A skeleton holds `pending` values and sources (`type: pending` in specs and observations, `kind: pending` in sources); the renderer refuses any file that still has them.

- Each requirement states its `intended_coverage`. Once its values are filled, the decision table must reproduce it; a test checks every filled requirement, so a value that silently changes a Coverage class fails CI.
- `uv run python -m traceq_dataset.world world/tp201.yaml` prints the pending list and the Coverage distribution against the target.
- `uv run python scripts/verify_quotes.py world/tp201.yaml` downloads each cited page and checks the quote (local only; CI has no network access).
- A file is frozen-ready only when nothing is pending, the decision table agrees, and every judged value has `reviewed_by`. The progress report lists judged values awaiting review and marks those without a supporting quote; those go to the design-partner review.
- The measure of sourcing quality is not the share of quoted values but that no number is frozen unless it is machine-checked against a quote or signed off by a human. Plant utilities and room data (voltage, air, temperature, ceiling height) can only come from a plant, so they are always judged values.

## 8. Generator pipeline

```
world/*.yaml ──Pydantic──▶ renderer ──▶ degrader (scans) ──▶ corpus (Release asset)
     │                                                        ├─ docs/…
     │                                                        └─ manifest.json
     └──────────────────── answer key ──────────────────────▶ answer_key/*.yaml
```

- **Renderer: Typst**, through the `typst` Python package pinned to an exact version in `pyproject.toml` (`traceq_dataset.render`). Chosen over WeasyPrint because:
  - it is a self-contained wheel locked by `uv.lock`; WeasyPrint needs system Pango/GTK libraries, which do not install with uv and fail on Windows development machines;
  - output is byte-identical for the same input, with system fonts ignored (bundled fonts only) and PDF metadata dates set to the document's issue date;
  - the renderer can query where content was placed (`metadata` + `here()`), which gives each requirement's page now and bounding boxes for the OCR answer key later (section 6).

  Python formats every string (numbers and dates in the document language); templates in `src/traceq_dataset/templates/` only lay it out, so the expected text is known exactly. Document number, revision, issue date and signatories are world data (`documents:`).
- **Degrader:** rasterise, skew 0.5–2°, noise, JPEG compression, stamps, handwritten entries in OFL fonts (e.g. Caveat, Kalam). Level set per document, not globally random. Nameplate photos are rendered synthetically.
- **Binary files are not committed.** The corpus is built in a container with pinned versions and published as a GitHub Release asset per dataset version. The release bytes are canonical, including for extraction cache keys (document hash + pipeline version).
- **CI** re-renders and runs a semantic validator, not a byte-hash comparison: every answer-key value appears in the rendered text; every defect location and citation exists; the required-document list matches the VMP; the denylist finds nothing.

## 9. Evals

### Split

Held out: TP-202 in full (different vendor and layout). A `generate --variant <seed>` command for random new Equipment follows in v2.

### Citations

A citation is `doc_id + revision + page + verbatim quote` (≤ 200 characters). Scoring is deterministic: the quote is found in the page text by fuzzy match (ratio ≥ 0.9) and the claimed value appears inside the quote. No LLM judge.

### Drafted Test Steps

An Acceptance Criterion in an AI-drafted Test Step may only be copied from a cited source (URS, vendor specification, pharmacopoeia). Without a source the field is left empty and flagged "to be set by a human". An unsourced AC counts as fabrication.

Each drafted Test Step is scored on six binary criteria:

| # | Criterion | Scored by |
|---|---|---|
| 1 | Traces to the right requirement | Deterministic |
| 2 | AC sourced, or flagged empty | Deterministic |
| 3 | Tests upper/lower limits or worst case (CPOB 12.29b) | LLM judge |
| 4 | Names the measuring instrument | LLM judge |
| 5 | Method is executable | LLM judge |
| 6 | Witness flag matches the SOP | Deterministic |

The judge is a single model (Claude Haiku) for both modes, binary with a written critique, calibrated against 40 human labels (20 outputs from each generator). Target TPR/TNR ≥ 0.9 per generator; if the two generators differ by more than 0.05, judge scores are not used to choose between models. In a real on-premises (Mode Pabrik) deployment the judge must also be local; this is recorded in the datasheet.

### Gates

- **Absolute floor of 0** for: fabricated AC, fabricated citation or Evidence, and any `gap` / `partial` / `conflict` requirement labelled `covered_by_vendor`.
- **Ratchet** for every other metric against the accepted baseline (the first Claude Haiku run sets the initial baseline).
- The same rules choose models and gate CI.
- About 10% of items are hallucination probes; fabrication rate is reported separately.

### Running

The CI gate scores recorded outputs (replay). A full live eval (Batch API) is required when the prompt, model, pipeline, or dataset (MAJOR/MINOR) changes. A new baseline lands through a PR that updates the baseline file and links the eval run. Eval size is about 150 cases.

## 10. Governance

- **Versioning:** SemVer in [`CHANGELOG.md`](../../CHANGELOG.md). MAJOR = answer-key semantics or schema change; MINOR = new Equipment or documents, or weight changes after discovery; PATCH = fixes. Every eval run records the dataset version.
- **Answer-key changes** go through their own PR with written rationale, a reference to the decision table, and a CHANGELOG entry. They are never combined with prompt changes. The TP-202 answer key changes only after the prompt is frozen.
- **Documentation:** [`DATASHEET.md`](../../DATASHEET.md) follows Datasheets for Datasets (Gebru et al.).
- **Licences:** code Apache-2.0; dataset and rendered documents CC BY 4.0.
- **Domain review:** one 30-minute session with the design partner after v0, covering the TP-201 URS and FAT, the Coverage decision table, and ambiguous judge labels.

## 11. Stages

| Version | Weeks | Contents | Unlocks |
|---|---|---|---|
| v0 | 1–2 | TP-201 package, 35–40 requirements, 8 planted scenarios | Thin end-to-end slice (weeks 3–4) |
| v1 | 3–5 | HSMG-101, FBD-101, CP-301: history, ~25-row registry, missing documents, Change Control | Registry, Requalification, missing-document recall |
| v2 | 5–6 | PW-001 phased PQ; TP-202 held out; `generate --variant` | Held-out eval, Mode Cloud vs Mode Pabrik |

## 12. Discovery parameters [D]

- Equipment types most often qualified: confirms the Equipment list.
- Most common review errors: defect-type weights.
- Reuse of vendor FAT/SAT: Coverage framing.
- Document language: ID/EN proportion.
- Working tools (Word / Excel / paper / DMS): format mix.
- Test Steps that require a Witness: which Test Steps are flagged critical.
- How protocols are written (template vs copied from similar Equipment): if copied, add the "leftover from another Equipment" defect.
