# Fixture: a Review Package run of TP-201-OQ-draft 0.1.0

Not a live run and not a baseline. The eight `protocol_draft` recordings (one per page of
`OQ-TP201` rev 0) were answered by a stand-in for the model that reads each page by line
patterns, so the replay test (`tests/test_recorded_runs.py`) can run a whole Review Package
run with zero live calls and no API spend (ticket #207). On page 1 the stand-in also returns
a reading whose quote is not on the page, which the citation check drops.

- `<key>.json`: the draft calls, keyed like every recording (document hash, pipeline version,
  prompt hash, model `claude-haiku-5-5`, request text). The Equipment calls are not here: the
  run replays them from `recordings/haiku-r10`.
- `ingest/`: Docling's reading of the rendered draft (the PDF of the package release, SHA-256
  in `recordings/TP-201-OQ-draft-0.1.0/manifest.json`), so the replay reads no PDF.
- `run.json`, `report.json`: the run metadata and the scorer report of the run that wrote
  them; the replay must reproduce them at tolerance 0.

A change to the draft prompt stops these recordings from replaying. The live Review Package
run (after the system tickets, with the owner's spend approval) records real answers in
`recordings/`; the replay test then points at it.
