"""Ingest: the documents of a released corpus, the text printed on each page and its tables."""

from traceq.documents.corpus import Corpus, CorpusDocument, normalise
from traceq.documents.ingest import INGEST_VERSION, Page, Table

__all__ = ["INGEST_VERSION", "Corpus", "CorpusDocument", "Page", "Table", "normalise"]
