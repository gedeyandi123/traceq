# Indonesian Pharmaceutical Equipment Qualification Context, Regulatory Baseline, and Benchmark

- **Date:** 28 November 2026
- **Scope:** Public-source research and cross-model gap analysis supporting TraceQ's general end-to-end demo and upcoming practitioner validation (`#245`). Strictly public sources only; no plant documents, held-out references, or real equipment vendor names ([ADR 0001](../adr/0001-portfolio-synthetic-data-only.md)).
- **Owner direction (28 November 2026):** `"setuju semua rekomendasimu"` — keep TraceQ focused on cross-document Pre-review with verified citations before `#245`, polish the general end-to-end demo (`A1–A5`) without migrations or lifecycle overengineering, and gate post-interview changes behind `#245`.

---

## 1. Regulatory Baseline in Indonesia (BPOM CPOB)

### 1.1. Current Regulation & Numbering Correction
The active Good Manufacturing Practice standard in Indonesia is **Peraturan BPOM No. 7 Tahun 2024** on *Standar Cara Pembuatan Obat yang Baik (CPOB)*, updated by **Peraturan BPOM No. 7 Tahun 2025** (primarily adjusting Sterile Annex 1 and annex structure).

- **Qualification & Validation is Chapter 12 (*Bab 12 — Kualifikasi dan Validasi*), NOT Annex 12.** In CPOB 2024, **Aneks 12** covers *Uji Pelulusan Real Time dan Pelulusan Parametris* (Real-Time Release Testing and Parametric Release), whereas EU GMP places qualification in Annex 15. `docs/design/synthetic-dataset.md` (§3) already cites `Ch. 12` accurately.
- **Computerized Systems is Annex 7 (*Aneks 7 — Sistem Komputerisasi*)**, closely mirroring EU GMP Annex 11 (2011).

### 1.2. Key Clauses Relevant to TraceQ
- **Bab 12 (Kualifikasi & Validasi):**
  - **12.13 & 12.28:** Installation Qualification (IQ/KI) and Operational Qualification (OQ/KO) may be executed separately or combined into a single qualification protocol (`KIO`). This directly supports combined IQ/OQ rows in [ADR 0012](../adr/0012-protocol-assembled-from-decided-proposals.md) (`R4` risk is lower than initially assumed, though practitioner confirmation in `#245` remains needed).
  - **12.14:** Plants must review and verify qualification protocols prepared by third parties (equipment vendors or validation contractors) prior to approval. This provides direct regulatory backing for [ADR 0010](../adr/0010-pre-review-of-site-documents-is-the-claim.md)'s core claim: pre-reviewing site/vendor protocols against URS and vendor evidence.
  - **12.16:** Out-of-criteria results during execution must be recorded and investigated as deviations. This aligns directly with [ADR 0013](../adr/0013-execution-results-judged-by-code-deviations-opened-by-code.md) (code-judged pass/fail and automatic Deviation opening).
  - **12.18:** Conditional approval to proceed to the next qualification stage is permitted under defined controls (currently unmodelled in TraceQ; deferred to `#245` / Keranjang B).
- **Bab 10 (Dokumentasi) & Data Integrity:**
  - **10.1:** Recognizes hybrid paper and electronic documentation systems.
  - **10.5:** Requires controls preventing the inadvertent use of obsolete or superseded documents (supporting TraceQ's `outdated_reference` check and stale-revision refusal).
  - References **WHO Good Data and Record Management Practices** (ALCOA+); no standalone BPOM data integrity guideline separate from CPOB Bab 10 / Aneks 7 was found.
  - A secondary review of 2020–2024 inspection literature identifies qualification, validation, and calibration among the most frequent major inspection findings.
- **Aneks 7 (Sistem Komputerisasi):**
  - **§3:** Formal agreements (including SLA/responsibilities) required with third-party IT/cloud service providers (relevant to Mode Cloud under [ADR 0004](../adr/0004-provider-agnostic-llm-two-modes.md)).
  - **§6:** Independent second-person verification (or validated technical control) for critical manually entered data.
  - **§8 (§8.1):** Systems must be able to produce clear, accurate printouts of electronically stored data — supporting printable Approved Protocol and Qualification Report PDFs.
  - **§9:** Non-erasable audit trails capturing GMP data creation/changes/deletion must be convertible into a human-readable form and periodically reviewed.
  - **§14:** Internal electronic signatures are recognized as equivalent to handwritten signatures within the company when permanently bound to their electronic record and stamped with date and time.
  - **§16:** Manual fallback procedures must exist when computerized systems fail.
- **Draft EU GMP Annex 22 & Annex 11 Revision Status (late November 2026):** Both remain drafts following the October 2025 public consultation (Annex 11 2011 remains operative; EU target finalization Q4 2026), and BPOM has not published standalone AI GMP guidance. [ADR 0002](../adr/0002-ai-advisory-only.md) and [ADR 0009](../adr/0009-non-critical-human-in-the-loop-under-draft-annex-22.md) (non-critical AI advisory with human-in-the-loop) remain well-positioned.

---

## 2. Observed & Reported Plant Workflow Context

- Indonesia has roughly **200–267 active CPOB-certified pharmaceutical manufacturing facilities** (~95% on Java, concentrated in West Java, Jakarta, and East Java).
- **Public primary literature on detailed day-to-day qualification workflows is thin**, consisting mainly of recent Indonesian academic/industry case studies (e.g., UHPLC IQ/OQ/PQ 2025, ampoule labelling machine DQ–PQ 2026, dry heat sterilizer PQ 2024).
- **Operational picture (n=1 practitioner baseline from `docs/design/synthetic-dataset.md`):**
  - Protocols and reports are authored in **Microsoft Word**, traceability matrices (RTM) and calculations in **Microsoft Excel**, and status/schedules tracked in spreadsheets and calendars without a dedicated validation DMS.
  - Controlled copies are printed for wet-ink review/approval by Engineering/Validation, User/Production, and Head of QA.
  - Execution binders commonly attach SI/KAN ISO 17025 calibration certificates, thermal/data logger printouts, HMI/nameplate photos, and paper Deviation/CAPA forms. Cleanrooms and classified production areas often restrict laptops/phones during execution, creating friction for live-only entry unless hybrid print/record workflows are supported.
  - Reuse of vendor FAT/SAT evidence is narrow and requires careful site verification.
  - Open field unknowns for `#245`: prevalence of internal e-signatures vs wet signatures, whether plants execute the reviewed draft or re-author internally (`R3`), who typically drafts the protocol (vendor vs internal team), and whether conditional stage release (Bab 12.18) is routine.

---

## 3. Adoption Barriers & Legal Context

1. **Cloud AI Policy vs On-Premises Hardware:**
   - **PP 71/2019** permits private electronic system operators (*PSE Lingkup Privat*) to process/store data outside Indonesia subject to regulatory compliance conditions, and distinguishes **PSrE-certified** (*Penyelenggara Sertifikasi Elektronik*) vs **non-certified** electronic signatures.
   - **UU PDP (Law No. 27/2022) Articles 56–57** regulate cross-border personal data transfers (adequacy, binding safeguards/SCC, or consent; administrative fines up to 2% of annual revenue). The Indonesian Constitutional Court (*Mahkamah Konstitusi*) rejected the judicial review challenge to Article 56 in January 2026 (an implementing Government Regulation is expected around 2027, not yet confirmed).
   - **Takeaway:** Cloud processing is **not flatly illegal**, but QA and IT teams conservatively resist sending unapproved plant documents to foreign LLM endpoints. Conversely, most domestic mid-to-large pharma plants lack enterprise data-center GPU servers for heavy self-hosted models.
   - **Middle-ground option for Mode Pabrik (`#343`, pending `#245` Q5):** Domestic Indonesian sovereign GPU cloud infrastructure (e.g., Indosat GPU Merdeka / Lintasarta, Sahabat-AI ecosystem) could satisfy data-residency preferences without requiring plant-owned GPU hardware. Do not build before `#245` answers Q5.
2. **Computerized System Validation (CSV) Burden:** Under Aneks 7, any system used for official GxP execution and e-signatures requires plant-side CSV documentation and infrastructure qualification. Positioning TraceQ initially as a non-critical pre-review aid reduces validation friction compared with replacing an entire eQMS.
3. **Decision-Making Unit (DMU):** Purchasing and adoption involve multiple stakeholders: **Validation/Engineering Manager** (technical champion), **Head of QA / Apoteker Penanggung Jawab Pemastian Mutu** (absolute compliance veto), **IT Manager** (security/hosting), and **Plant/Operations Director** (budget). Inviting a QA perspective alongside a Validation Supervisor to `#245` addresses `D14`.

---

## 4. Competitive Benchmark & TraceQ Positioning

*Note: Competitor capabilities below reflect public vendor claims and third-party listings as of late 2026 and are not independently verified.*

| Dimension | Manual (Word / Excel / Paper) | Enterprise e-Validation (Kneat Gx, ValGenesis VLMS, Veeva, MasterControl) | TraceQ Realistic Moat |
|---|---|---|---|
| **Cost & Footprint** | Low software cost; high review effort & BPOM audit risk | High enterprise cost & long CSV implementation (e.g., MasterControl QMS estimated from ~USD 25k/yr on third-party listings); geared toward MNCs | Lightweight, focused tool for mid-to-large Indonesian plants without forcing full eQMS replacement |
| **AI Role** | None | Kneat AI Review Assistant reviews single execution documents at a time (cross-document review on roadmap to 2027); ValGenesis sells AI protocol authoring, gap assessment, and anomaly detection (no Indonesian language support) | **Cross-document Pre-review (`URS ↔ vendor Datasheet/DQ/FAT/SAT ↔ site draft`) with page-verified citations + deterministic rules** |
| **Indonesian Fit** | Matches local wet-signature habits | English-first, FDA/EMA-oriented, assumes full paperless transition | **Indonesian-native, aligned with CPOB 2024 Bab 12 & Aneks 7, offline/self-hosted capable, hybrid digital ↔ printable PDF** |

**Strategic implication:** Execution, Deviation management, and full eQMS workflows are incumbents' strongest territory. Investing heavily there before practitioner validation (`#245`) puts TraceQ in direct competition where it holds no moat. TraceQ's differentiator is catching defects *before* approval across URS, vendor evidence, and site drafts with zero-fabrication citations.

---

## 5. Consolidated Gap Analysis (Pre-`#245` Demo vs Post-`#245` Scope)

### Keranjang A — High-Impact General Demo Polish (`A1–A5`, Zero DB Migrations, $0 Live Cost)
1. **A1 — UX & Friction Polish:** Configurable UI display timezone in **WIB (`Asia/Jakarta`)** while keeping DB and calibration inputs explicitly UTC; web forms for `ExclusiveRange` and `ToleranceBand` (`#426`); neutral post-approval banner without stale `"langkah 6"` / `"step 6, not yet built"` wording; sweep remaining raw English UI enums. *(Note: URS page 2 text cleanup and `iq_protocol` label in `#145` are already fixed on `main` via PR `#372`.)*
2. **A2 — Clickable Draft Protocol (`OQ-TP201`) PDF Citations:** Serve uploaded/package draft PDF bytes via composition root resolver (`src/traceq/app/api.py`) respecting ADR 0008 layer boundaries, and enable `PdfCitationButton` in `DraftStepDrawer.tsx`.
3. **A3 — Draft-Aware `demo_seed.py` Fast-Forward (`#439`) + Free ($0) `409` Demo:** Enable seeding from-draft Protocols through Execution/Report (`K84`, `K83` from-draft) and demonstrating `409 pinned_behind` using recorded `Rev 0` → `Rev 1` uploads at zero live API cost.
4. **A4 — Printable Approved Protocol PDF (`protocol_v1.typ`) & Enriched Qualification Report PDF (`v3.0.0`):** Render printable Approved Protocol PDF directly from the frozen copy (small ADR 0012 amendment lifting `"no printed or exported Protocol"`), and enrich Qualification Report `v3.0.0` (keeping `v1`/`v2` frozen) with Acceptance Criteria, observed values, instrument IDs & calibration due dates, evidence text refs, and Deviation Investigation/CAPA already stored in `ExecutionCopy`.
5. **A5 — Read-Only Audit Trail Screen (`/audit`):** Paginated, filtered read-only `GET /audit` endpoint + `/audit` Web UI over existing `audit_trail` rows (Aneks 7 §9), without claiming ADR 0007 Phase 3 hash chains.

### Keranjang B — Deferred Until Practitioner Validation (`#245`)
- Validation of `R1–R3` (revision-round bottleneck, three new defect types, whether plants execute the reviewed draft, who authors drafts).
- Execution file attachments (photos, printouts, calibration certificates) and paper-to-digital transcription workflows.
- Separating IQ vs OQ Protocols, post-approval Protocol versioning/requalification, and conditional stage release (Bab 12.18).
- Strict SoD rules (`uploader_approves`), `409 pinned_behind` policy, mandatory Witness rules, and Retest gating (`R5`/`R6`).
- Official PDF/calibration timezone policy (WIB vs UTC), PSrE vs internal e-signatures (PP 71/2019), Cloud vs domestic GPU vs on-prem (`#343`), direct `.docx` ingestion, prompt/rule changes (`#145` Path B, `#431`, Indonesian AI reasons), and purchasing authority (`D14`).

### Keranjang C — Scope Creep Traps (Do Not Build Now)
- PQ modules, process/cleaning validation, full eQMS (Change Control, cross-dept CAPA, training, DMS), and ERP/LIMS/CMMS integrations.
- Full AI protocol authoring, GPU self-hosting (`#343b`), arbitrary browser uploads without eval sets (`#342` closed/narrowed), mobile/offline apps, multi-site tenancy.
- Full CSV validation package, ADR 0007 Phase 3 hash chains/external object-lock, and pre-pilot hardening (`#428–#432`, `#437`).

---

## 6. Primary & Reference Sources

- **PerBPOM No. 7 Tahun 2024 (Official CPOB Text):** https://peraturan.go.id/files/peraturan-bpom-no-7-tahun-2024.pdf
- **BPOM Press Release on PerBPOM No. 7 Tahun 2025:** https://www.pom.go.id/siaran-pers/tingkatkan-standar-keamanan-dan-kualitas-obat-yang-beredar-bpom-perbarui-standar-cara-pembuatan-obat-yang-baik
- **CSV Review (Majalah Farmasetika, Unpad):** https://jurnal.unpad.ac.id/farmasetika/article/download/69580/27337
- **BPOM Inspection Findings Literature Review (Jurnal Ners):** https://journal.universitaspahlawan.ac.id/index.php/ners/article/download/50790/31507/179288
- **Indonesian Qualification Case Studies (Unpad Farmasetika):** UHPLC IQ/OQ/PQ (https://jurnal.unpad.ac.id/farmasetika/article/view/62299) and Ampoule Labelling Machine DQ–PQ (https://jurnal.unpad.ac.id/farmasetika/article/view/70795)
- **PP 71/2019 & UU PDP Article 56 Constitutional Court Ruling (Hukumonline):** https://www.hukumonline.com/berita/a/mengenal-pokok-pokok-aturan-baru-pp-pste-lt5de653d86d627/?page=all and https://www.hukumonline.com/berita/a/transfer-data-lintas-negara-dan-ilusi-pelindungan-data-pribadi-pasca-putusan-mk-lt6981468330d9c?page=all
- **Certified Electronic Signatures / PSrE (Hukumonline):** https://www.hukumonline.com/berita/a/cepat-belum-tentu-aman--pentingnya-tanda-tangan-elektronik-tersertifikasi-lt68f4e9ec7ba3f
- **Indonesia Sovereign GPU Cloud Context (NVIDIA Blog):** https://blogs.nvidia.com/blog/indonesia-tech-leaders-sovereign-ai
- **Competitor References (Vendor Claims / Third-Party Estimates):** Kneat AI (https://kneat.com/kneat-ai/), ValGenesis AI & Validation Whitepaper (https://www.valgenesis.com/solution/ai-powered-validation, https://www.valgenesis.com/editorial/ensuring-trust-in-ai-the-valgenesis-approach-to-validating-ai-agents-and-functions-for-validation-and-qualification-in-life-sciences), Veeva Validation Story (https://www.veeva.com/customer-stories/astrazeneca-preparing-for-rapid-manufacturing-growth-with-unified-digital-validation/), MasterControl Pricing Estimate (https://www.capterra.com/compare/148577-178567/MasterControl-vs-Vault-Quality-Suite)
- **EU GMP Annex 11 & Annex 22 2026 Revision Status (Epista):** https://www.epista.com/knowledge/preparing-for-emas-2026-good-manufacturing-practice-gmp-revisions-chapter-4-annex-11-annex-22
