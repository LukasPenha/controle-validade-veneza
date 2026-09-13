-- ATUALIZAÇÃO DO BANCO EXISTENTE, SEM APAGAR LOTES OU USUÁRIOS.
BEGIN;
SET LOCAL search_path TO public;
DO $$ BEGIN
IF NOT EXISTS (SELECT 1 FROM public.alembic_version WHERE version_num IN ('20260909_v2','20260909_setores')) THEN
RAISE EXCEPTION 'Versão diferente da esperada. Não reaplique a atualização.';
END IF; END $$;
-- Execute no SQL Editor do banco atual. Não apaga nem altera os setores existentes.
INSERT INTO public.setor (nome)
VALUES ('Padaria'), ('Açougue'), ('Mercearia'), ('Frios'),
       ('Bebidas'), ('Higiene e limpeza')
ON CONFLICT (nome) DO NOTHING;

ALTER TABLE produto ADD COLUMN custo_unitario NUMERIC(12, 2);

ALTER TABLE produto ADD COLUMN arquivado BOOLEAN DEFAULT false NOT NULL;

ALTER TABLE produto DROP CONSTRAINT ck_produto_quantidade;

ALTER TABLE produto ADD CONSTRAINT ck_produto_quantidade CHECK (quantidade >= 0);

ALTER TABLE produto ADD CONSTRAINT ck_produto_custo CHECK (custo_unitario IS NULL OR custo_unitario >= 0);

ALTER TABLE produto DROP CONSTRAINT ck_produto_source;

ALTER TABLE produto ADD CONSTRAINT ck_produto_source CHECK (source IN ('openfoodfacts','manual'));

CREATE TABLE movimento (
    id SERIAL NOT NULL,
    produto_id INTEGER NOT NULL,
    request_key VARCHAR(64) NOT NULL,
    tipo VARCHAR(15) NOT NULL,
    quantidade INTEGER NOT NULL,
    custo_unitario NUMERIC(12, 2),
    valor_unitario NUMERIC(12, 2),
    motivo VARCHAR(255) NOT NULL,
    actor VARCHAR(254) NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_movimento_quantidade CHECK (quantidade > 0),
    CONSTRAINT ck_movimento_tipo CHECK (tipo IN ('venda','descarte','devolucao')),
    CONSTRAINT ck_movimento_custo CHECK (custo_unitario IS NULL OR custo_unitario >= 0),
    CONSTRAINT ck_movimento_valor CHECK (valor_unitario IS NULL OR valor_unitario >= 0),
    FOREIGN KEY(produto_id) REFERENCES produto (id) ON DELETE RESTRICT,
    UNIQUE (request_key)
);

CREATE INDEX ix_movimento_produto_id ON movimento (produto_id);

CREATE INDEX ix_movimento_timestamp ON movimento (timestamp);

CREATE TABLE audit_event (
    id SERIAL NOT NULL,
    produto_id INTEGER NOT NULL,
    loja_id INTEGER NOT NULL,
    setor_id INTEGER NOT NULL,
    actor VARCHAR(254) NOT NULL,
    action VARCHAR(30) NOT NULL,
    changes JSON NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id)
);

CREATE INDEX ix_audit_event_produto_id ON audit_event (produto_id);

CREATE INDEX ix_audit_event_loja_id ON audit_event (loja_id);

CREATE INDEX ix_audit_event_timestamp ON audit_event (timestamp);

CREATE TABLE login_limit (
    key VARCHAR(64) NOT NULL,
    attempts INTEGER NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (key)
);

CREATE INDEX ix_login_limit_expires_at ON login_limit (expires_at);

DO $$ DECLARE role_name text; BEGIN
        FOREACH role_name IN ARRAY ARRAY['anon','authenticated'] LOOP
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname=role_name) THEN
            EXECUTE format('REVOKE ALL ON TABLE public.usuario, public.produto, public.loja,
            public.setor, public.notificacao, public.notificacao_lida, public.email_preference,
            public.email_token, public.email_delivery, public.job_state, public.external_lookup_cache,
            public.api_budget, public.movimento, public.audit_event, public.login_limit,
            public.alembic_version FROM %I', role_name);
          END IF;
        END LOOP; END $$;

UPDATE alembic_version SET version_num='20260912_operacao';
COMMIT;
