# Temporal for orchestration; the database owns business dates

Qualification is full of long waits (a water PQ of at least 12 months, Requalification due dates, Execution over weeks), so orchestration uses Temporal: durable workflows, long timers, and a history UI that helps both the demo and audits. Business dates (due dates, PQ phases) are stored in the database as the queryable, auditable source of truth; Temporal only runs the timers and orchestration derived from them and receives a signal when a date changes.

## Considered Options

- Celery: sync-first, needs patches for async code (FastAPI, LLM clients).
- Taskiq / Procrastinate: async-native but young.
- DBOS (durable workflows in Postgres, no extra server): lighter, but younger, with month-long timers not publicly proven. The candidate replacement if the on-premises component count must shrink.

## Amended 16 November 2026 (ADR 0010)

Temporal is deferred, not rejected. "The database owns business dates" stays: what is due is a query on the Equipment Registry. No workflow in the ten-week plan waits across days in a way a query and one worker process cannot serve. Pre-review of a new document version is a background job; its mechanics are decided in that slice's spec. Interactive Pre-review calls the model API directly, at about twice the Batch price; eval runs stay on the Batch API.
