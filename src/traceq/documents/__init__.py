"""Ingest: the documents of a released corpus, the text printed on each page, its tables and
the entries the OCR model read on a scan."""

from traceq.documents.cache import IngestCache, Ingested
from traceq.documents.corpus import VERSIONS, Corpus, CorpusDocument, normalise
from traceq.documents.pages import OcrLine, Page, Table
from traceq.documents.scan import OcrUnavailable

__all__ = [
    "VERSIONS",
    "Corpus",
    "CorpusDocument",
    "IngestCache",
    "Ingested",
    "OcrLine",
    "OcrUnavailable",
    "Page",
    "Table",
    "normalise",
]
