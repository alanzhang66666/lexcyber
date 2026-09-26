-- V20: runtime-role grants for the app schema.
--
-- Objects created by the migrator role (lex_migrator) — including everything
-- on installs where the app-migrate service runs the migrations — are not
-- automatically accessible to the runtime role lex_app. This migration grants
-- CRUD on all current objects and sets default privileges for future
-- migrator-created objects.
--
-- The statements are defensive so the same file applies whether it runs as
-- the schema owner, the migrator/superuser, or a least-privilege role:

DO $$
DECLARE
    has_app      boolean := EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'lex_app');
    has_migrator boolean := EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'lex_migrator');
BEGIN
    IF NOT has_app THEN
        RETURN;
    END IF;

    -- Grant on existing objects. Requires ownership or superuser; when the
    -- caller owns the objects the statements are no-ops but still succeed.
    -- If the caller lacks privilege (e.g. lex_app against migrator-owned
    -- objects), warn instead of failing — the migrator-run path applies them.
    BEGIN
        EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA app TO lex_app';
        EXECUTE 'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA app TO lex_app';
    EXCEPTION WHEN insufficient_privilege THEN
        RAISE WARNING 'V20: skipped table grants; apply as schema owner or lex_migrator';
    END;

    -- Default privileges so future objects created by the migrator role are
    -- accessible to lex_app. ALTER DEFAULT PRIVILEGES FOR ROLE requires
    -- superuser or membership in the target role.
    IF has_migrator AND (
        SELECT rolsuper OR pg_has_role(current_user, 'lex_migrator', 'USAGE')
        FROM pg_roles WHERE rolname = current_user
    ) THEN
        EXECUTE 'ALTER DEFAULT PRIVILEGES FOR ROLE lex_migrator IN SCHEMA app
                 GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO lex_app';
        EXECUTE 'ALTER DEFAULT PRIVILEGES FOR ROLE lex_migrator IN SCHEMA app
                 GRANT USAGE, SELECT ON SEQUENCES TO lex_app';
    END IF;
END $$;
