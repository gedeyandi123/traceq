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

### Changed

- Principles 5 and 7: values may be copied by an LLM from a cited source, never produced from memory; real vendor brochures are not cited.
