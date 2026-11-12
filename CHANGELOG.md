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
- TP-201 values: all requirements, FAT/SAT observations and datasheet facts filled; the decision table reproduces every intended Coverage class. 11 values are quoted (PerBPOM 7/2024, PIC/S PI 041-1, ECA, a journal citing Permenaker 5/2018); 27 are site decisions drafted by an LLM, 12 of them with a supporting quote (Pharmaceutics 2020, 2023, 2025), all awaiting human review.
- Schema: `Source.drafted_by` and `reviewed_by`; `Equipment.unreviewed()` lists judged values without sign-off, and the progress report is frozen-ready only when that list is empty.
- TP-201 values: all 38 requirements, FAT/SAT observations and datasheet facts filled. 21 sources carry a verbatim quote (PerBPOM 7/2024, Pharmaceutics 2020, ECA, a journal citing Permenaker 5/2018); the rest are site decisions with rationale. The decision table reproduces every intended Coverage class.

### Changed

- Principles 5 and 7: values may be copied by an LLM from a cited source, never produced from memory; real vendor brochures are not cited.
