# TraceQ

Traceability-led workspace for pharmaceutical equipment qualification (GMP), with AI as an advisory assistant. The plant, vendors, people, and documents are fictional; all data is synthetic.

Status: early. Work starts with the synthetic dataset that drives the demo and the evals.

- [`GLOSSARY.md`](GLOSSARY.md): domain language
- [`docs/design/synthetic-dataset.md`](docs/design/synthetic-dataset.md): dataset design
- [`DATASHEET.md`](DATASHEET.md), [`CHANGELOG.md`](CHANGELOG.md): dataset documentation and versions

## Licence

Code: [Apache-2.0](LICENSE). Dataset and rendered documents: [CC BY 4.0](LICENSE-DATA).

## Development

```sh
pip install pre-commit
pre-commit install
```

Tests: `uv sync && uv run pytest`.

Render: `uv run python -m traceq_dataset.render world/tp201.yaml [--t0 YYYY-MM-DD] [--out dist]`. Output goes to `dist/` (gitignored); the corpus is published as a Release asset, never committed.

Hooks: ruff, gitleaks, and a denylist check. The denylist blocks real equipment vendor names (`denylist/public.txt`) and private terms kept in a gitignored `.denylist.local` file (CI reads them from the `DENYLIST` secret).

Workflow: short branches (`feat/`, `fix/`, `docs/`, `chore/`), [Conventional Commits](https://www.conventionalcommits.org/), squash-merge via PR.
