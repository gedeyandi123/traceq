"""The Audit Trail: who did what to which record, when, and why (ADR 0007, spec #105).

Append-only. The application can add an entry and read entries; Postgres refuses it anything
else (``traceq.db`` migrations). The time is the database clock, never the application's.
"""

from traceq.audit.trail import Actor, Entry, Json, append, entries

__all__ = ["Actor", "Entry", "Json", "append", "entries"]
