# TraceQ

Traceability-led workspace for pharmaceutical equipment qualification (GMP), with AI as an advisory assistant. The plant, vendors, people, and documents are fictional; all data is synthetic.

Status: the synthetic dataset v0 (TP-201 package and its answer key) and the eval scorer are in place; the TraceQ system itself is next, starting with a thin slice that turns the TP-201 package into a scored submission. The dataset is not frozen yet: judged values await practitioner review.

- [`GLOSSARY.md`](GLOSSARY.md): domain language
- [`docs/adr/`](docs/adr/): architecture decisions
- [`CLAUDE.md`](CLAUDE.md): development protocol for coding agents
- [`docs/design/synthetic-dataset.md`](docs/design/synthetic-dataset.md): dataset design
- [`DATASHEET.md`](DATASHEET.md), [`CHANGELOG.md`](CHANGELOG.md): dataset documentation and versions

## Licence

Code: [Apache-2.0](LICENSE). Dataset and rendered documents: [CC BY 4.0](LICENSE-DATA). The handwriting font Caveat (`src/traceq_dataset/fonts/`) is under the [SIL Open Font License 1.1](src/traceq_dataset/fonts/OFL-Caveat.txt).

## Development

```sh
pip install pre-commit
pre-commit install
```

Tests: `uv sync && uv run pytest`. Types: `uv run pyright`.

Render: `uv run python -m traceq_dataset.render world/tp201.yaml [--t0 YYYY-MM-DD] [--seed N] [--out dist]`. Paper documents (`scan:` in world data) are written only as their scan. Output goes to `dist/` (gitignored) with the corpus `manifest.json`; the corpus is published as a Release asset, never committed.

Answer key: `uv run python -m traceq_dataset.answer_key world/tp201.yaml [--check]` derives `answer_key/TP-201/*.yaml` from world data and the eval corpus. Never edit it by hand; regenerate it after changing world data or the renderer (`--check` and the tests fail on a stale key).

Eval: `uv run python -m traceq_eval world/tp201.yaml submission.json [--out report]` scores a recorded system output against the answer key and writes `report.json` and `report.md`; it exits 1 when a gate fails. `--baseline baselines/TP-201.json` adds the ratchet against the accepted baseline and `--write-baseline` writes a candidate (design section 9, "Gates", "Running" and "Scorer").

Run: `uv run traceq run dist/t0-2026-06-01 [--equipment TP-201] [--out runs] [--recordings recordings]` writes `runs/<run id>/submission.json`, `matrix.json` (Coverage class, reason and cited Evidence per requirement), `drafts.json` (drafted IQ/OQ Test Steps as AI Findings pending review; an Acceptance Criterion only when copied from a verified citation, otherwise empty and flagged "to be set by a human") and `run.json` (settings, model, prompt hashes, tokens, cost in USD). Test Steps are drafted for requirements the vendor did not cover; `--no-vendor-reuse` drafts one for every requirement ("could be saved by reuse"), but eval runs keep the default, which scorer criterion 1 assumes. Born-digital PDFs are read with Docling on the CPU (its models download from Hugging Face on first use), spreadsheets with openpyxl, and scans with the local OCR model PP-OCRv6 small via RapidOCR 3.10.0, an optional dependency (`uv sync --extra ocr`). Ingest output is cached in `<recordings>/ingest` by document hash and reader version, so a replay with a filled cache runs neither Docling nor the OCR model; `run.json` logs seconds per page and peak RAM per document read. It replays recorded LLM calls and sends nothing; `--live` sends unrecorded calls to Claude through the Batch API (`ANTHROPIC_API_KEY`) and records them, refusing before sending when the estimate passes `--max-usd` (default 1). Module boundaries are checked by import-linter (`uv run lint-imports`, also run by the tests).

Serve: `uv run traceq serve [--runs runs] [--corpus dist/t0-2026-06-01]` starts the read-only API over the run folders (GET only; it reads `run.json` and `matrix.json` of a run and the documents the run read, never anything else in the folder). The UI in `web/` (Next.js, Bahasa Indonesia via next-intl) shows the traceability matrix with Evidence links that open the cited page: `cd web && npm ci && npm run dev`, with the API at `TRACEQ_API_URL` (default `http://127.0.0.1:8000`; the `/api` rewrite reads it at build time). The TypeScript client is generated from the OpenAPI schema: after an API change run `npm run openapi && npm run generate` in `web/` and commit both files (`tests/test_api.py` and CI fail on a stale schema or client). Web checks: `npm run typecheck`, `npm test`.

Eval screen: scores come from the harness, never from the system's API. Score a run into its folder (`uv run python -m traceq_eval world/tp201.yaml runs/<run id>/submission.json --out runs/<run id>`), then `uv run python -m traceq_eval.screen serve [--runs runs] [--port 8001]` serves, per scored run, each rate with k/n and its split (dev TP-201, held-out otherwise), the gate verdict and the run's cost; never report items or baselines. The UI reads it at `TRACEQ_EVAL_URL` (default `http://127.0.0.1:8001`); its client is generated from `web/eval-openapi.json` by the same `npm run openapi && npm run generate` (`tests/test_eval_screen.py` fails on a stale schema).

Hooks: ruff, gitleaks, and a denylist check. The denylist blocks real equipment vendor names (`denylist/public.txt`) and private terms kept in a gitignored `.denylist.local` file (CI reads them from the `DENYLIST` secret).

Workflow: short branches (`feat/`, `fix/`, `docs/`, `chore/`, `test/`, `refactor/`), [Conventional Commits](https://www.conventionalcommits.org/), squash-merge via PR. A spec is built on an integration branch that reaches `main` in one PR ([`CLAUDE.md`](CLAUDE.md)).
