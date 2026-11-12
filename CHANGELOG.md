# Changelog

Dataset versions follow [SemVer](https://semver.org/):

- **MAJOR:** answer-key semantics or schema change.
- **MINOR:** new Equipment or documents, or defect-weight changes after discovery.
- **PATCH:** fixes.

Every eval run records the dataset version. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- Dataset design, glossary, datasheet skeleton, and licences (code Apache-2.0, data CC BY 4.0).
- `traceq_dataset` package: world-data schema (Pydantic), T0 date offsets, and the `covered_by_vendor` decision table with tests.
- TP-201 world-data skeleton (`world/tp201.yaml`): 38 URS requirements with intended Coverage, FAT/SAT protocols and steps, and the eight v0 scenarios. Values and sources are still `pending`.
- Schema: two-tier `Source` (quoted: `url`, `quote`, `accessed`; site decision: `rationale`), value-in-quote check, `pending` placeholders, and the `Equipment` model with cross-reference checks.
- `python -m traceq_dataset.world` progress report and `scripts/verify_quotes.py` (local quote check).
- TP-201 values: all requirements, FAT/SAT observations and datasheet facts filled; the decision table reproduces every intended Coverage class. 11 values are quoted (PerBPOM 7/2024, PIC/S PI 041-1, ECA, a journal citing Permenaker 5/2018); 27 are site decisions drafted by an LLM, 12 of them with a supporting quote (Pharmaceutics 2020, 2023, 2025). Owner review signed off 17 of the 27; the other 10 await the practitioner and block freeze.
- Schema: `Source.drafted_by` and `reviewed_by`; `Equipment.unreviewed()` lists judged values without sign-off, and the progress report is frozen-ready only when that list is empty.
- Renderer (Typst, `typst==0.15.2`): `python -m traceq_dataset.render world/tp201.yaml` renders URS-TP201 rev 0 and rev 1 (SKP, Indonesian) for a given T0 (eval T0 2026-06-01). Rev 0 uses `superseded_spec` (S8). Output is deterministic and records each requirement's page.
- Schema: `Document` (number, revision, language, issue date, signatories, change note) with person and revision checks; TP-201 URS rev 0 (T0-260d) and rev 1 (T0-215d).
- Semantic validator (`traceq_dataset.validate`): every requirement sentence must appear on its recorded page.
- FAT renderer: FAT-TP201-M (mechanical) and FAT-TP201-C (control system) as combined protocol-and-report vendor documents in English. S4 renders as an empty site check/approval block; S5 as 96 kN against "≥ 100 kN" recorded Pass. Each step's acceptance criterion and result are placed and validated.
- Schema: `TestEvidence.description` and `acceptance` (the vendor's own AC where it is narrower than the URS); `Equipment.serial_no`; `Document` type `fat` whose site approval must match its protocol.
- SAT renderer: SAT-TP201 as a printed English vendor form with bilingual headings, filled in by hand at site (Caveat, OFL) in Indonesian number and date formats, with a vendor stamp. Planted: S1 SAT-01 output overwritten 121.400 → 122.400 tablets/h with no initials or date; S2 tachometer TACH-07 calibration valid until T0-15d, SAT executed T0-14d; S3 serial RTP36-25-0471 against nameplate RTP36-25-0417; S7 SAT-03 "1.500 rpm".
- Handwritten entries record a bounding box (`Placed.box`, pt, top-left origin, padded for slanted-glyph overhang) for the OCR answer key; the validator checks each one inside its box (pypdfium2). The degrader (rasterise, skew, noise, JPEG) follows separately and only transforms pixels and boxes.
- Degrader (`traceq_dataset.degrade`): paper documents are published as image-only scans (rasterise, skew, paper tone, blur, noise, JPEG) at a per-document level (`Document.scan`; SAT-TP201 `medium`: 150 dpi, skew 0.8–1.4°). Handwritten boxes become skewed quads (`ScannedPlaced.quad`) for the OCR answer key. Deterministic per seed (`render --seed`, default 0); the validator checks no text layer and ink inside every quad.
- `Rendered.issued`: the issue date, used as the metadata date of scans as well.
- Schema: `Instrument` with `CalibrationCertificate`, `TestEvidence.instruments` and `correction`, `Document` type `sat` with `entry_language` and a per-document `serial_no`; SAT step descriptions.
- Answer key (`traceq_dataset.answer_key`, committed under `answer_key/TP-201/`), derived from world data and the rendered eval corpus (T0 2026-06-01, seed 0): `requirements.yaml` (38 requirements: location, normalised value, S8 superseded value, Evidence per step with the first failing decision-table condition, expected Coverage and reason), `defects.yaml` (D-TP201-001 to -007 for S1–S7: type, severity, layer, reference, expected finding, locations with quads on the scan), `ambiguous.yaml` (S7 `1.500 rpm` with both readings; expected answer "ask for confirmation"), `documents.yaml` (14 required documents: in corpus, planned, or expected gap for IQ/OQ), `ocr.yaml` (every handwritten SAT entry with its quad). `--check` fails on a stale key.
- Schema: `Scenario.finding` (`DefectType`, severity, detail, anchors by placed field or printed text) and `Equipment.required_documents` with a `missing` reason; anchors, required documents and rendered documents are cross-checked.
- Validator `answer_key_problems`: checks a committed answer key against a freshly rendered corpus (value on its page, placed field and quad match, planned documents really unrendered, required documents match the corpus).
- Corpus (`traceq_dataset.corpus`): builds all documents and scans of an Equipment; `render` writes the corpus `manifest.json` (version, T0, seed, library versions; per file path, format, pages, size, SHA-256) and accepts several world files.
- TP-201 design documents and certificates:
  - DS-TP201: vendor technical datasheet (English, dense tables), 23 design facts plus the nameplate serial (S3). Values are copied from the URS spec, except the output (36 × 70 × 60 = 151,200 tablets/h) and tooling EU B (`conflict` with URS-TP201-008).
  - MTC-TP201-01: 3.1 material certificate (EN 10204), scan `medium`, five product-contact parts; S6 is the feed frame housing in SS 304 (1.4301) among SS 316L parts.
  - KAL-2025-0412 (TACH-07, valid until T0-15d, S2) and KAL-2026-0057 (SW-03): calibration certificates from a fictional lab, scan `light`, with a results table.
  - DQ-TP201: design qualification report (Indonesian, clean) reviewing URS rev 1 against the datasheet; it records the tooling mismatch as an open item.
- Rest of the TP-201 package; only IQ/OQ remain outside the corpus (`expected_gap`):
  - RA-TP201: site risk assessment as an XLSX short FMEA (Indonesian, clean), one row per URS rev 1 requirement with failure mode, effect, S/O/D (1–5), RPN and Critical Aspect. Severity ≥ 4 marks a Critical Aspect and must match `critical` in the URS (schema check; 11 requirements). Scores and threshold are drafted by an LLM and block freeze until reviewed.
  - FDS-TP201: vendor functional design specification (English, born-digital, clean), one function per control and data-integrity requirement, including the untested door interlock, recipe backup and time synchronisation (still `gap`). No URS numbers and no values beyond the URS spec and datasheet.
  - CAL-TP201-01: the vendor's calibration certificate for the press's compression force measuring system (main and pre-compression channels), scan `light`, clean: calibrated before the FAT, valid through the SAT, largest main-channel error 0.42 kN (≤ FAT-M-08's 0.5% FS). Readings drafted by an LLM, awaiting review.
- Schema: `Equipment.risk_assessment` (`RiskAssessment`, `Risk`); `Document` types `functional_spec` and `risk_assessment` (which reviews a URS revision); `DesignEvidence.description`; `CalibrationPoint.channel`; a certificate may be issued by the vendor.
- Renderer: XLSX output (openpyxl, values not formulas, zip and property dates fixed to the issue date). `Rendered.data` and `format`; `Placed.sheet` and `cell`. The validator checks spreadsheet cells; the manifest records `format: xlsx` and `sheets`; `openpyxl` joins the recorded generator versions.
- Answer key re-derived: each requirement carries its `risk` row (sheet, row, Critical Aspect, scores), control and data-integrity requirements gain FDS `design_evidence`, RA/FDS/CAL are `in_corpus`, and `ocr.yaml` lists the new scan. No Coverage class, defect or ambiguous value changed. The validator checks every `risk` entry against the spreadsheet.
- Schema: `Document` types `datasheet`, `material_certificate`, `calibration_certificate`, `dq_report` with per-type checks; `DesignEvidence.label` and `section`; `Organisation` (`Equipment.labs`), `Equipment.model` and `site_name`; personas `vendor_inspector` and `lab_staff`; `CalibrationCertificate.lab` and `results` (readings drafted by an LLM block freeze until reviewed, `Equipment.unreviewed_results()`).
- `coverage.meets` accepts a design range: it meets the URS when it spans the whole URS range.

### Changed

- Answer key: datasheet, material certificate and calibration certificates are located, so S2, S3 and S6 point at placed fields (`valid_until`, `serial`, `item-2.material`) instead of `status: planned`; `design_evidence` carries page, field, text and, on a certificate, the part. S6 detail now names the feed frame housing. Still planned: RA-TP201, FDS-TP201, CAL-TP201-01.
- Principles 5 and 7: values may be copied by an LLM from a cited source, never produced from memory; real vendor brochures are not cited.
