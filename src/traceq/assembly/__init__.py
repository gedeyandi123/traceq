"""The Protocol assembled in TraceQ from a run's decided Proposals (spec #247, ADR 0012).

Named apart from ``traceq.protocols``, which drafts the IQ/OQ Test Steps, and its record types
avoid a bare ``Protocol``, which ``traceq.traceability.coverage`` uses for vendor FAT/SAT
protocols. In text: "a Protocol in Draft status", never "Protocol Draft" (the site's document).

``lifecycle`` starts and withdraws a Protocol and reads its status events; ``rows`` computes its
rows live from the run's Proposals and their standings; ``api`` holds the routes.
"""
