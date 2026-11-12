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
