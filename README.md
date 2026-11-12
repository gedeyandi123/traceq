# TraceQ

Traceability-led workspace for pharmaceutical equipment qualification (GMP), with AI as an advisory assistant. The plant, vendors, people, and documents are fictional; all data is synthetic.

Status: early. Work starts with the synthetic dataset that drives the demo and the evals.

- [`GLOSSARY.md`](GLOSSARY.md): domain language
- [`docs/design/synthetic-dataset.md`](docs/design/synthetic-dataset.md): dataset design
- [`DATASHEET.md`](DATASHEET.md), [`CHANGELOG.md`](CHANGELOG.md): dataset documentation and versions

## Licence

Code: [Apache-2.0](LICENSE). Dataset and rendered documents: [CC BY 4.0](LICENSE-DATA). The handwriting font Caveat (`src/traceq_dataset/fonts/`) is under the [SIL Open Font License 1.1](src/traceq_dataset/fonts/OFL-Caveat.txt).

## Development

```sh
pip install pre-commit
pre-commit install
```

Tests: `uv sync && uv run pytest`.

Render: `uv run python -m traceq_dataset.render world/tp201.yaml [--t0 YYYY-MM-DD] [--seed N] [--out dist]`. Paper documents (`scan:` in world data) are written only as their scan. Output goes to `dist/` (gitignored) with the corpus `manifest.json`; the corpus is published as a Release asset, never committed.

Answer key: `uv run python -m traceq_dataset.answer_key world/tp201.yaml [--check]` derives `answer_key/TP-201/*.yaml` from world data and the eval corpus. Never edit it by hand; regenerate it after changing world data or the renderer (`--check` and the tests fail on a stale key).

Eval: `uv run python -m traceq_eval world/tp201.yaml submission.json [--out report]` scores a recorded system output against the answer key and writes `report.json` and `report.md`; it exits 1 when a gate fails. `--baseline baselines/TP-201.json` adds the ratchet against the accepted baseline and `--write-baseline` writes a candidate (design section 9, "Gates", "Running" and "Scorer").

Hooks: ruff, gitleaks, and a denylist check. The denylist blocks real equipment vendor names (`denylist/public.txt`) and private terms kept in a gitignored `.denylist.local` file (CI reads them from the `DENYLIST` secret).

Workflow: short branches (`feat/`, `fix/`, `docs/`, `chore/`), [Conventional Commits](https://www.conventionalcommits.org/), squash-merge via PR.
