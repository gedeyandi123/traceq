# Portfolio with a design partner; synthetic and public data only

TraceQ is a public portfolio project. A practising qualification supervisor at a pharmaceutical plant is its design partner: a source of domain review, not a buyer and not a data source. All data describes a fictional plant built from public sources (CPOB, WHO TRS, literature) until a plant gives written permission; no internal document, name or format enters this repository or is sent to an LLM. This protects the design partner from a confidentiality breach and keeps the work publishable.

## Consequences

- A denylist blocks real vendor names (`denylist/public.txt`) and private terms (a gitignored local file and the `DENYLIST` CI secret), in files, PR and issue text, and commit messages.
- Values without a public source are site decisions that a human reviews before the dataset freezes (design §2, principle 7).
- Amended 14 November 2026: the goal is a portfolio that opens a path to a product. The ten-week plan and budget stay; real-plant use is answered by [`docs/pilot-readiness.md`](../pilot-readiness.md), not by a pilot. A private eval set from a plant is planned there and starts only after written permission, with the data and model kept on site.
- Public real documents (vendor datasheets, tender specifications, URS templates with a clear licence) may test the document reader only: they have no answer key and produce no Coverage rate. Only their URL, hash and measurements are committed, unless their licence allows redistribution.
