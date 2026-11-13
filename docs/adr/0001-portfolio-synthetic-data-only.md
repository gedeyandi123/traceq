# Portfolio with a design partner; synthetic and public data only

TraceQ is a public portfolio project. A practising qualification supervisor at a pharmaceutical plant is its design partner: a source of domain review, not a buyer and not a data source. All data describes a fictional plant built from public sources (CPOB, WHO TRS, literature) until a plant gives written permission; no internal document, name or format enters this repository or is sent to an LLM. This protects the design partner from a confidentiality breach and keeps the work publishable.

## Consequences

- A denylist blocks real vendor names (`denylist/public.txt`) and private terms (a gitignored local file and the `DENYLIST` CI secret), in files, PR and issue text, and commit messages.
- Values without a public source are site decisions that a human reviews before the dataset freezes (design §2, principle 7).
