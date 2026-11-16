"""The Audit Trail the application cannot alter (spec #105, "Audit Trail"; ADR 0007 phase 1).

Driven through SQL against a real Postgres: what the application role may do, and what the
database refuses. Each test session migrates its own database from zero (``tests/conftest.py``).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from conftest import Databases
from sqlalchemy import URL, create_engine, text
from sqlalchemy.exc import DBAPIError, ProgrammingError

from traceq.audit import Actor, append, entries
from traceq.db import engine, transaction

ALICE = Actor(subject="sub-1", issuer="http://127.0.0.1:9000", name="Persona Satu")
REFUSING = (
    "UPDATE audit_trail SET reason = 'rewritten'",
    "DELETE FROM audit_trail",
    "TRUNCATE audit_trail",
)


def _seed(url: URL) -> None:
    with transaction(engine(url)) as s:
        append(s, ALICE, "run imported", "run", "r1", new={"proposals": 47})


def test_the_application_appends_and_reads_entries(databases: Databases) -> None:
    with transaction(engine(databases.app)) as s:
        e = append(
            s,
            ALICE,
            "decision recorded",
            "proposal",
            "p1",
            old={"class": "covered"},
            new={"class": "gap"},
            reason="the cited value is out of range",
        )
    with transaction(engine(databases.app)) as s:
        found = [x for x in entries(s) if x.id == e.id]
    assert found == [e]
    assert (e.actor, e.action, e.record_type, e.record_id) == (
        ALICE,
        "decision recorded",
        "proposal",
        "p1",
    )
    assert (e.old_value, e.new_value, e.reason) == (
        {"class": "covered"},
        {"class": "gap"},
        "the cited value is out of range",
    )
    assert e.at.tzinfo is not None


def test_time_comes_from_the_database_clock(databases: Databases) -> None:
    with engine(databases.app).begin() as c:
        c.execute(
            text(
                "INSERT INTO audit_trail (at, subject, issuer, name, action, record_type,"
                " record_id) VALUES ('2000-01-01', 's', 'i', 'n', 'a', 't', 'x')"
            )
        )
        at = c.execute(text("SELECT at FROM audit_trail WHERE record_id = 'x'")).scalar_one()
    assert at > datetime(2020, 1, 1, tzinfo=UTC)


@pytest.mark.parametrize("statement", REFUSING)
def test_the_application_role_has_no_grant_to_alter(databases: Databases, statement: str) -> None:
    _seed(databases.app)
    with (
        pytest.raises(ProgrammingError, match="permission denied"),
        engine(databases.app).begin() as c,
    ):
        c.execute(text(statement))


@pytest.mark.parametrize("statement", REFUSING)
def test_a_trigger_refuses_even_a_role_with_the_grant(databases: Databases, statement: str) -> None:
    """The owner holds every grant, so only the trigger stands in its way."""
    _seed(databases.app)
    with pytest.raises(DBAPIError, match="append-only"), engine(databases.owner).begin() as c:
        c.execute(text(statement))
    with transaction(engine(databases.app)) as s:
        assert entries(s)


def test_migrations_from_zero_leave_grants_and_triggers(fresh_database: Databases) -> None:
    with create_engine(fresh_database.owner).connect() as c:
        grants = c.execute(
            text(
                "SELECT privilege_type FROM information_schema.role_table_grants"
                " WHERE table_name = 'audit_trail' AND grantee = 'traceq_app'"
            )
        ).scalars()
        triggers = c.execute(
            text(
                "SELECT DISTINCT event_manipulation FROM information_schema.triggers"
                " WHERE event_object_table = 'audit_trail' AND action_timing = 'BEFORE'"
            )
        ).scalars()
        truncate = c.execute(
            text(
                "SELECT count(*) FROM pg_trigger WHERE tgrelid = 'audit_trail'::regclass"
                " AND tgtype & 32 = 32"
            )
        ).scalar_one()
        assert sorted(grants) == ["INSERT", "SELECT"]
        assert {"UPDATE", "DELETE"} <= set(triggers)
        assert truncate == 1


# --- The decisions table: the same protection ------------------------------------------
DECISION_REFUSING = (
    "UPDATE proposal_decisions SET reason = 'rewritten'",
    "DELETE FROM proposal_decisions",
    "TRUNCATE proposal_decisions",
)


def _seed_decision(url: URL) -> None:
    """One imported run, one Proposal and a decision on it, added as the application role."""
    with engine(url).begin() as c:
        c.execute(
            text(
                "INSERT INTO imported_runs (run_id, equipment, created, model, mode,"
                " pipeline_version, prompts, documents) VALUES"
                " ('r-seed', 'TP-000', now(), 'm', 'replay', '1', '{}', '[]')"
            )
        )
        pid = c.execute(
            text(
                "INSERT INTO proposals (kind, equipment, subject, subject_hash, ordinal)"
                " VALUES ('ai', 'TP-000', '{}', md5(random()::text), 0) RETURNING id"
            )
        ).scalar_one()
        c.execute(
            text(
                "INSERT INTO run_proposals (run_id, proposal_id, seq, position, content_hash,"
                " proposed) VALUES ('r-seed', :p, 0, 0, 'h', '{}') ON CONFLICT DO NOTHING"
            ),
            {"p": pid},
        )
        c.execute(
            text(
                "INSERT INTO proposal_decisions (proposal_id, run_id, content_hash, decision,"
                " subject, issuer, name) VALUES (:p, 'r-seed', 'h', 'accepted', 's', 'i', 'n')"
            ),
            {"p": pid},
        )


@pytest.fixture(scope="module")
def decided(new_database: Callable[[], Databases]) -> Databases:
    dbs = new_database()
    _seed_decision(dbs.app)
    return dbs


@pytest.mark.parametrize("statement", DECISION_REFUSING)
def test_the_application_role_cannot_alter_a_decision(decided: Databases, statement: str) -> None:
    with (
        pytest.raises(ProgrammingError, match="permission denied"),
        engine(decided.app).begin() as c,
    ):
        c.execute(text(statement))


@pytest.mark.parametrize("statement", DECISION_REFUSING)
def test_a_trigger_refuses_altering_a_decision_even_with_the_grant(
    decided: Databases, statement: str
) -> None:
    with pytest.raises(DBAPIError, match="append-only"), engine(decided.owner).begin() as c:
        c.execute(text(statement))
    with engine(decided.app).connect() as c:
        assert c.execute(text("SELECT count(*) FROM proposal_decisions")).scalar_one() == 1


def test_a_decision_takes_the_database_clock(decided: Databases) -> None:
    with engine(decided.app).connect() as c:
        at = c.execute(text("SELECT at FROM proposal_decisions")).scalar_one()
    assert at > datetime(2020, 1, 1, tzinfo=UTC)


def test_migrations_from_zero_protect_the_decisions_table(fresh_database: Databases) -> None:
    with create_engine(fresh_database.owner).connect() as c:
        grants = c.execute(
            text(
                "SELECT privilege_type FROM information_schema.role_table_grants"
                " WHERE table_name = 'proposal_decisions' AND grantee = 'traceq_app'"
            )
        ).scalars()
        triggers = c.execute(
            text(
                "SELECT DISTINCT event_manipulation FROM information_schema.triggers"
                " WHERE event_object_table = 'proposal_decisions' AND action_timing = 'BEFORE'"
            )
        ).scalars()
        truncate = c.execute(
            text(
                "SELECT count(*) FROM pg_trigger"
                " WHERE tgrelid = 'proposal_decisions'::regclass AND tgtype & 32 = 32"
            )
        ).scalar_one()
        assert sorted(grants) == ["INSERT", "SELECT"]
        assert {"UPDATE", "DELETE"} <= set(triggers)
        assert truncate == 1
