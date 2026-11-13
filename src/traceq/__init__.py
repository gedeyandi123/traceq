"""TraceQ, the system under test: reads a released corpus and writes a run folder.

Modules (ADR 0008): ``documents`` (ingest, page text), ``traceability`` (segmentation,
extraction, citation check), ``ai`` (the LLM port, its Mode Cloud adapter, record/replay and
cost) and ``runs`` (CLI and run folder). import-linter enforces the layering.
"""
