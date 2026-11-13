# Temporal for orchestration; the database owns business dates

Qualification is full of long waits (a water PQ of at least 12 months, Requalification due dates, Execution over weeks), so orchestration uses Temporal: durable workflows, long timers, and a history UI that helps both the demo and audits. Business dates (due dates, PQ phases) are stored in the database as the queryable, auditable source of truth; Temporal only runs the timers and orchestration derived from them and receives a signal when a date changes.

## Considered Options

- Celery: sync-first, needs patches for async code (FastAPI, LLM clients).
- Taskiq / Procrastinate: async-native but young.
- DBOS (durable workflows in Postgres, no extra server): lighter, but younger, with month-long timers not publicly proven. The candidate replacement if the on-premises component count must shrink.
