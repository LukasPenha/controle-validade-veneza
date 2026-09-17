-- UNIÃO DOS SETORES EM MERCEARIA, PRESERVANDO OS REGISTROS.
BEGIN;
SET LOCAL search_path TO public;
DO $$ BEGIN
IF NOT EXISTS (SELECT 1 FROM public.alembic_version WHERE version_num='20260913_exposicao') THEN
RAISE EXCEPTION 'Versão diferente da esperada. Não reaplique a atualização.';
END IF; END $$;
INSERT INTO setor (nome) VALUES ('Mercearia') ON CONFLICT (nome) DO NOTHING;

UPDATE produto SET setor_id=(SELECT id FROM setor WHERE nome='Mercearia'), exposure_revision=exposure_revision+1 WHERE setor_id IN (SELECT id FROM setor WHERE lower(trim(nome)) IN ('bebidas','higiene e limpeza'));

UPDATE usuario SET setor_id=(SELECT id FROM setor WHERE nome='Mercearia') WHERE setor_id IN (SELECT id FROM setor WHERE lower(trim(nome)) IN ('bebidas','higiene e limpeza'));

UPDATE notificacao SET setor_id=(SELECT id FROM setor WHERE nome='Mercearia') WHERE setor_id IN (SELECT id FROM setor WHERE lower(trim(nome)) IN ('bebidas','higiene e limpeza'));

UPDATE audit_event SET setor_id=(SELECT id FROM setor WHERE nome='Mercearia') WHERE setor_id IN (SELECT id FROM setor WHERE lower(trim(nome)) IN ('bebidas','higiene e limpeza'));

DELETE FROM setor WHERE id IN (SELECT id FROM setor WHERE lower(trim(nome)) IN ('bebidas','higiene e limpeza'));

UPDATE alembic_version SET version_num='20260916_mercearia';
COMMIT;
