-- ATUALIZAÇÃO: FOTOS DA EXPOSIÇÃO. Execute após atualizar_20260912.sql.
BEGIN;
SET LOCAL search_path TO public;
DO $$ BEGIN
IF NOT EXISTS (SELECT 1 FROM public.alembic_version WHERE version_num='20260912_operacao') THEN
RAISE EXCEPTION 'Versão diferente da esperada. Não reaplique a atualização.';
END IF; END $$;
ALTER TABLE produto ADD COLUMN exposure_revision INTEGER DEFAULT '1' NOT NULL;

CREATE TABLE exposure_proof (
    id SERIAL NOT NULL, 
    produto_id INTEGER NOT NULL, 
    revision INTEGER NOT NULL, 
    actor VARCHAR(254) NOT NULL, 
    note VARCHAR(255) NOT NULL, 
    quantidade INTEGER NOT NULL, 
    validade DATE NOT NULL, 
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL, 
    image_sha VARCHAR(64) NOT NULL, 
    image_data BYTEA NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_exposure_image UNIQUE (produto_id, revision, image_sha), 
    CONSTRAINT ck_exposure_size CHECK (length(image_data) <= 524288), 
    FOREIGN KEY(produto_id) REFERENCES produto (id) ON DELETE RESTRICT
);

CREATE INDEX ix_exposure_current ON exposure_proof (produto_id, revision);

DO $$ DECLARE role_name text; BEGIN
        FOREACH role_name IN ARRAY ARRAY['anon','authenticated'] LOOP
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname=role_name) THEN
            EXECUTE format('REVOKE ALL ON TABLE public.exposure_proof FROM %I', role_name);
          END IF;
        END LOOP; END $$;

UPDATE alembic_version SET version_num='20260913_exposicao';
COMMIT;
