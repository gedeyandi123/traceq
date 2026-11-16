-- The two server roles of TraceQ (spec #105, "Audit Trail"). Idempotent, safe to run from two
-- sessions at once; nothing ever drops them. Run as a role that may create roles: Compose
-- start-up (compose.yaml) and the test fixture (tests/conftest.py, also in CI).
DO $roles$
BEGIN
  BEGIN
    CREATE ROLE traceq_owner LOGIN CREATEDB PASSWORD 'traceq_owner';
  EXCEPTION WHEN duplicate_object OR unique_violation THEN NULL;
  END;
  BEGIN
    CREATE ROLE traceq_app LOGIN PASSWORD 'traceq_app';
  EXCEPTION WHEN duplicate_object OR unique_violation THEN NULL;
  END;
END
$roles$;
