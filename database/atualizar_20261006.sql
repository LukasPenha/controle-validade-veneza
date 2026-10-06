-- FALHAS DOS JOBS, PERMISSÕES PADRÃO E RLS. Execute após atualizar_20260916.sql.
BEGIN;
SET LOCAL search_path TO public;
DO $$ BEGIN
IF NOT EXISTS (SELECT 1 FROM public.alembic_version WHERE version_num='20260916_mercearia') THEN
RAISE EXCEPTION 'Versão diferente da esperada. Não reaplique a atualização.';
END IF; END $$;
ALTER TABLE job_state ADD COLUMN last_error VARCHAR(255);

ALTER TABLE job_state ADD COLUMN failures INTEGER DEFAULT '0' NOT NULL;

DO $$ DECLARE role_name text; table_name text; BEGIN
        FOREACH role_name IN ARRAY ARRAY['anon','authenticated'] LOOP
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname=role_name) THEN
            EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM %I', role_name);
            EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM %I', role_name);
            EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA public FROM %I', role_name);
            EXECUTE format('REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM %I', role_name);
          END IF;
        END LOOP;
        FOR table_name IN SELECT tablename FROM pg_tables WHERE schemaname='public' AND tableowner=current_user LOOP
          EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', table_name);
        END LOOP; END $$;

UPDATE alembic_version SET version_num='20261006_seguranca';
COMMIT;
