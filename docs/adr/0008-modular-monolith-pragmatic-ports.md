# Modular monolith by domain; ports only where there really are two implementations

The backend is one FastAPI deployable split into domain modules (registry, documents, traceability, protocols, execution, review, signatures, audit, ai, runs, app, proposals, identity, db). Each module has its own router, schemas, service and models behind a small public interface; module boundaries are enforced by import-linter in CI once the modules exist, and typing is checked by pyright (in CI since traceq#21; product packages in strict mode). This avoids a pattern where routes, schemas and models pile up in single large files.

Ports and adapters exist only where two real implementations exist. The LLM port has two: Mode Cloud and Mode Pabrik (ADR 0004). Storage (S3 API), identity (OIDC, ADR 0005) and workflow (Temporal, ADR 0006) are used directly through their standard protocols, with no extra abstraction layer.

**OCR: no port.** ADR 0004 keeps OCR local in both modes, so an OCR port cannot be split by mode. The thin-slice spec decided: one local OCR model, called directly. A port appears only when a second implementation enters the product. If ADR 0004 is ever replaced, OCR moves behind the existing LLM port.

The `runs` module holds the run folder and the read-only API over run folders (added in #29).

**Amended 16 November 2026 (spec #105).** `app` holds the CLI and composes the API application; `runs` no longer holds the CLI. `proposals`, `audit`, `identity` and `db` join the module list. Layers, top to bottom: `app` > `proposals` > `audit`, `identity` > `db` > `runs` > `review`, `protocols` > `traceability` > `documents`, `ai`. The reason is the dependency direction: `proposals` reads the run-folder schemas of `runs`, so the application and the CLI that start both must sit above both. A second import-linter contract forbids the modules below from importing `app`; each ticket that creates a module adds it to both contracts.

## Considered Options

- Microservices / Kubernetes: rejected, overengineering for one person and a 10-week demo.
- A port for every external dependency: rejected, an abstraction without a second implementation only adds code.
