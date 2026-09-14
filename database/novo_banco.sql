-- INSTALAÇÃO NOVA. Não execute no banco existente.
BEGIN;

CREATE TABLE loja (
	id SERIAL NOT NULL,
	nome VARCHAR(100) NOT NULL,
	cnpj VARCHAR(18),
	endereco VARCHAR(255),
	cidade VARCHAR(100),
	estado VARCHAR(2),
	PRIMARY KEY (id),
	UNIQUE (nome),
	UNIQUE (cnpj)
);

CREATE TABLE setor (
	id SERIAL NOT NULL,
	nome VARCHAR(50) NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (nome)
);

CREATE TABLE job_state (
	name VARCHAR(80) NOT NULL,
	last_success_at TIMESTAMP WITH TIME ZONE,
	PRIMARY KEY (name)
);

CREATE TABLE external_lookup_cache (
	key VARCHAR(64) NOT NULL,
	payload JSON NOT NULL,
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (key)
);

CREATE INDEX ix_external_lookup_cache_expires_at ON external_lookup_cache (expires_at);

CREATE TABLE api_budget (
	name VARCHAR(30) NOT NULL,
	next_allowed_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (name)
);

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

CREATE INDEX ix_audit_event_timestamp ON audit_event (timestamp);

CREATE INDEX ix_audit_event_produto_id ON audit_event (produto_id);

CREATE INDEX ix_audit_event_loja_id ON audit_event (loja_id);

CREATE TABLE login_limit (
	key VARCHAR(64) NOT NULL,
	attempts INTEGER NOT NULL,
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (key)
);

CREATE INDEX ix_login_limit_expires_at ON login_limit (expires_at);

CREATE TABLE usuario (
	id SERIAL NOT NULL,
	username VARCHAR(254) NOT NULL,
	password_hash VARCHAR(128) NOT NULL,
	role VARCHAR(50) NOT NULL,
	loja_id INTEGER,
	setor_id INTEGER,
	PRIMARY KEY (id),
	CONSTRAINT ck_usuario_role CHECK (role IN ('gerente_geral','gerente_trocas','gerente','encarregado_setor','auxiliar_gestao')),
	CONSTRAINT ck_usuario_loja CHECK (role IN ('gerente_geral','gerente_trocas') OR loja_id IS NOT NULL),
	CONSTRAINT ck_usuario_setor CHECK (role != 'encarregado_setor' OR setor_id IS NOT NULL),
	FOREIGN KEY(loja_id) REFERENCES loja (id) ON DELETE RESTRICT,
	FOREIGN KEY(setor_id) REFERENCES setor (id) ON DELETE RESTRICT
);

CREATE INDEX ix_usuario_loja_id ON usuario (loja_id);

CREATE INDEX ix_usuario_setor_id ON usuario (setor_id);

CREATE UNIQUE INDEX uq_usuario_username_lower ON usuario (lower(username));

CREATE TABLE produto (
	id SERIAL NOT NULL,
	nome_produto VARCHAR(200) NOT NULL,
	barcode VARCHAR(14) NOT NULL,
	plu VARCHAR(50) NOT NULL,
	source VARCHAR(30) NOT NULL,
	source_url VARCHAR(255) NOT NULL,
	marca VARCHAR(150) NOT NULL,
	lote VARCHAR(80) NOT NULL,
	quantidade INTEGER NOT NULL,
	custo_unitario NUMERIC(12, 2),
	arquivado BOOLEAN DEFAULT false NOT NULL,
	exposure_revision INTEGER DEFAULT '1' NOT NULL,
	validade DATE NOT NULL,
	status VARCHAR(50) NOT NULL,
	data_cadastro TIMESTAMP WITH TIME ZONE NOT NULL,
	motivo_rebaixa VARCHAR(255),
	loja_id INTEGER NOT NULL,
	setor_id INTEGER NOT NULL,
	criado_por_id INTEGER,
	PRIMARY KEY (id),
	CONSTRAINT ck_produto_quantidade CHECK (quantidade >= 0),
	CONSTRAINT ck_produto_custo CHECK (custo_unitario IS NULL OR custo_unitario >= 0),
	CONSTRAINT ck_produto_status CHECK (status IN ('Para Rebaixa','Em Rebaixa')),
	CONSTRAINT ck_produto_source CHECK (source IN ('openfoodfacts','manual')),
	FOREIGN KEY(loja_id) REFERENCES loja (id) ON DELETE RESTRICT,
	FOREIGN KEY(setor_id) REFERENCES setor (id) ON DELETE RESTRICT,
	FOREIGN KEY(criado_por_id) REFERENCES usuario (id) ON DELETE SET NULL
);

CREATE INDEX ix_produto_loja_setor_validade ON produto (loja_id, setor_id, validade);

CREATE INDEX ix_produto_validade ON produto (validade);

CREATE INDEX ix_produto_criado_por_id ON produto (criado_por_id);

CREATE INDEX ix_produto_barcode ON produto (barcode);

CREATE INDEX ix_produto_status_validade ON produto (status, validade);

CREATE TABLE email_preference (
	user_id INTEGER NOT NULL,
	address VARCHAR(254) NOT NULL,
	verified BOOLEAN NOT NULL,
	enabled BOOLEAN NOT NULL,
	frequency VARCHAR(10) NOT NULL,
	weekday INTEGER NOT NULL,
	hour INTEGER NOT NULL,
	minute INTEGER NOT NULL,
	days_min INTEGER NOT NULL,
	days_max INTEGER NOT NULL,
	PRIMARY KEY (user_id),
	CONSTRAINT ck_email_frequency CHECK (frequency IN ('daily','weekly')),
	CONSTRAINT ck_email_weekday CHECK (weekday BETWEEN 0 AND 6),
	CONSTRAINT ck_email_time CHECK (hour BETWEEN 0 AND 23 AND minute BETWEEN 0 AND 59),
	CONSTRAINT ck_email_window CHECK (days_min >= 0 AND days_max >= days_min AND days_max <= 365),
	FOREIGN KEY(user_id) REFERENCES usuario (id) ON DELETE CASCADE
);

CREATE INDEX ix_email_schedule ON email_preference (enabled, verified, frequency, weekday, hour);

CREATE TABLE email_token (
	digest VARCHAR(64) NOT NULL,
	user_id INTEGER NOT NULL,
	purpose VARCHAR(10) NOT NULL,
	address VARCHAR(254) NOT NULL,
	password_stamp VARCHAR(64) NOT NULL,
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
	used BOOLEAN NOT NULL,
	PRIMARY KEY (digest),
	CONSTRAINT ck_token_purpose CHECK (purpose IN ('reset','verify')),
	FOREIGN KEY(user_id) REFERENCES usuario (id) ON DELETE CASCADE
);

CREATE INDEX ix_email_token_expires_at ON email_token (expires_at);

CREATE INDEX ix_token_user_purpose ON email_token (user_id, purpose, used);

CREATE TABLE email_delivery (
	id SERIAL NOT NULL,
	delivery_key VARCHAR(160) NOT NULL,
	user_id INTEGER NOT NULL,
	kind VARCHAR(10) NOT NULL,
	recipient VARCHAR(254) NOT NULL,
	subject VARCHAR(200) NOT NULL,
	body TEXT NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	scheduled_for TIMESTAMP WITH TIME ZONE NOT NULL,
	status VARCHAR(10) NOT NULL,
	attempts INTEGER NOT NULL,
	next_attempt_at TIMESTAMP WITH TIME ZONE NOT NULL,
	started_at TIMESTAMP WITH TIME ZONE,
	sent_at TIMESTAMP WITH TIME ZONE,
	last_error VARCHAR(160),
	PRIMARY KEY (id),
	CONSTRAINT ck_delivery_status CHECK (status IN ('pending','sending','sent','skipped','cancelled','expired','failed','uncertain')),
	CONSTRAINT ck_delivery_attempts CHECK (attempts >= 0),
	UNIQUE (delivery_key),
	FOREIGN KEY(user_id) REFERENCES usuario (id) ON DELETE CASCADE
);

CREATE INDEX ix_delivery_pending ON email_delivery (status, next_attempt_at);

CREATE INDEX ix_delivery_user_created ON email_delivery (user_id, created_at);

CREATE TABLE notificacao (
	id SERIAL NOT NULL,
	event_key VARCHAR(160) NOT NULL,
	produto_id INTEGER NOT NULL,
	loja_id INTEGER NOT NULL,
	setor_id INTEGER NOT NULL,
	kind VARCHAR(30) NOT NULL,
	severity VARCHAR(10) NOT NULL,
	mensagem TEXT NOT NULL,
	timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
	resolved_at TIMESTAMP WITH TIME ZONE,
	PRIMARY KEY (id),
	CONSTRAINT ck_notificacao_severity CHECK (severity IN ('info','warning','critical')),
	UNIQUE (event_key),
	FOREIGN KEY(produto_id) REFERENCES produto (id) ON DELETE CASCADE,
	FOREIGN KEY(loja_id) REFERENCES loja (id) ON DELETE CASCADE,
	FOREIGN KEY(setor_id) REFERENCES setor (id) ON DELETE CASCADE
);

CREATE INDEX ix_notificacao_produto_id ON notificacao (produto_id);

CREATE INDEX ix_notificacao_scope ON notificacao (loja_id, setor_id, resolved_at, timestamp);

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

CREATE TABLE notificacao_lida (
	usuario_id INTEGER NOT NULL,
	notificacao_id INTEGER NOT NULL,
	read_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (usuario_id, notificacao_id),
	FOREIGN KEY(usuario_id) REFERENCES usuario (id) ON DELETE CASCADE,
	FOREIGN KEY(notificacao_id) REFERENCES notificacao (id) ON DELETE CASCADE
);
-- Execute no SQL Editor do banco atual. Não apaga nem altera os setores existentes.
INSERT INTO public.setor (nome)
VALUES ('Padaria'), ('Açougue'), ('Mercearia'), ('Frios'),
       ('Bebidas'), ('Higiene e limpeza')
ON CONFLICT (nome) DO NOTHING;

CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY);
INSERT INTO alembic_version VALUES ('20260913_exposicao');
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


DO $$ DECLARE role_name text; BEGIN
        FOREACH role_name IN ARRAY ARRAY['anon','authenticated'] LOOP
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname=role_name) THEN
            EXECUTE format('REVOKE ALL ON TABLE public.exposure_proof FROM %I', role_name);
          END IF;
        END LOOP; END $$;


COMMIT;
