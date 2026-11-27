"""The largest values the database's integer columns hold, for the API to bound what it takes:
a number beyond them is a 422, not a database error (audit C9/S8)."""

BIGINT_MAX = 2**63 - 1
"""``bigint``: every identity id (Protocols, Proposals, events, upload jobs)."""
INTEGER_MAX = 2**31 - 1
"""``integer``: document revision numbers."""
