"""Estado de falha dos jobs, permissões padrão e RLS para a Data API do Supabase."""
from alembic import op
import sqlalchemy as sa

revision = '20261006_seguranca'
down_revision = '20260916_mercearia'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('job_state', sa.Column('last_error', sa.String(255)))
    op.add_column('job_state', sa.Column('failures', sa.Integer(), nullable=False, server_default='0'))
    if op.get_bind().dialect.name == 'postgresql':
        # Tabelas futuras criadas por este usuário já nascem sem acesso para os papéis
        # públicos da Data API. RLS sem políticas bloqueia anon/authenticated; o dono
        # das tabelas (o próprio servidor Flask) não é afetado.
        op.execute("""DO $$ DECLARE role_name text; table_name text; BEGIN
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
        END LOOP; END $$""")


def downgrade():
    op.drop_column('job_state', 'failures')
    op.drop_column('job_state', 'last_error')
