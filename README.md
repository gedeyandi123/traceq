# TraceQ

Traceability-led workspace for pharmaceutical equipment qualification (GMP), with AI as an advisory assistant. The plant, vendors, people, and documents are fictional; all data is synthetic.

Status: early. Work starts with the synthetic dataset that drives the demo and the evals.

## Development

```sh
pip install pre-commit
pre-commit install
```

Hooks: ruff, gitleaks, and a denylist check. The denylist blocks real equipment vendor names (`denylist/public.txt`) and private terms kept in a gitignored `.denylist.local` file (CI reads them from the `DENYLIST` secret).

Workflow: short branches (`feat/`, `fix/`, `docs/`, `chore/`), [Conventional Commits](https://www.conventionalcommits.org/), squash-merge via PR.
