-- PostgreSQL hardening for append-only audit_log.
-- Run this after schema migration in production.

CREATE OR REPLACE FUNCTION prevent_audit_log_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION 'audit_log is append-only';
END;
$$;

DROP TRIGGER IF EXISTS trg_prevent_audit_log_update ON audit_log;
DROP TRIGGER IF EXISTS trg_prevent_audit_log_delete ON audit_log;

CREATE TRIGGER trg_prevent_audit_log_update
BEFORE UPDATE ON audit_log
FOR EACH ROW
EXECUTE FUNCTION prevent_audit_log_mutation();

CREATE TRIGGER trg_prevent_audit_log_delete
BEFORE DELETE ON audit_log
FOR EACH ROW
EXECUTE FUNCTION prevent_audit_log_mutation();

-- Optional least-privilege hardening example.
-- REVOKE UPDATE, DELETE ON audit_log FROM app_user;
