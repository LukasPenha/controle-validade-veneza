"""Baixas, custos, auditoria e proteção de login, preservando os lotes existentes."""
from alembic import op
import sqlalchemy as sa

revision = '20260912_operacao'
down_revision = '20260909_setores'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('produto') as batch:
        batch.add_column(sa.Column('custo_unitario',sa.Numeric(12,2),nullable=True))
        batch.add_column(sa.Column('arquivado',sa.Boolean(),server_default=sa.false(),nullable=False))
        batch.drop_constraint('ck_produto_quantidade',type_='check')
        batch.create_check_constraint('ck_produto_quantidade','quantidade >= 0')
        batch.create_check_constraint('ck_produto_custo','custo_unitario IS NULL OR custo_unitario >= 0')
        batch.drop_constraint('ck_produto_source',type_='check')
        batch.create_check_constraint('ck_produto_source',"source IN ('openfoodfacts','manual')")
    op.create_table('movimento',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('produto_id',sa.Integer(),sa.ForeignKey('produto.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('request_key',sa.String(64),nullable=False,unique=True),
        sa.Column('tipo',sa.String(15),nullable=False),
        sa.Column('quantidade',sa.Integer(),nullable=False),
        sa.Column('custo_unitario',sa.Numeric(12,2)),
        sa.Column('valor_unitario',sa.Numeric(12,2)),
        sa.Column('motivo',sa.String(255),nullable=False),
        sa.Column('actor',sa.String(254),nullable=False),
        sa.Column('timestamp',sa.DateTime(timezone=True),nullable=False),
        sa.CheckConstraint('quantidade > 0',name='ck_movimento_quantidade'),
        sa.CheckConstraint("tipo IN ('venda','descarte','devolucao')",name='ck_movimento_tipo'),
        sa.CheckConstraint('custo_unitario IS NULL OR custo_unitario >= 0',name='ck_movimento_custo'),
        sa.CheckConstraint('valor_unitario IS NULL OR valor_unitario >= 0',name='ck_movimento_valor'))
    op.create_index('ix_movimento_produto_id','movimento',['produto_id'])
    op.create_index('ix_movimento_timestamp','movimento',['timestamp'])
    op.create_table('audit_event',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('produto_id',sa.Integer(),nullable=False),
        sa.Column('loja_id',sa.Integer(),nullable=False),
        sa.Column('setor_id',sa.Integer(),nullable=False),
        sa.Column('actor',sa.String(254),nullable=False),
        sa.Column('action',sa.String(30),nullable=False),
        sa.Column('changes',sa.JSON(),nullable=False),
        sa.Column('timestamp',sa.DateTime(timezone=True),nullable=False))
    for field in ('produto_id','loja_id','timestamp'):
        op.create_index('ix_audit_event_'+field,'audit_event',[field])
    op.create_table('login_limit',
        sa.Column('key',sa.String(64),primary_key=True),
        sa.Column('attempts',sa.Integer(),nullable=False),
        sa.Column('expires_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_login_limit_expires_at','login_limit',['expires_at'])
    if op.get_bind().dialect.name == 'postgresql':
        # The Flask server uses its own DB credentials; these are Supabase Data API roles.
        op.execute("""DO $$ DECLARE role_name text; BEGIN
        FOREACH role_name IN ARRAY ARRAY['anon','authenticated'] LOOP
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname=role_name) THEN
            EXECUTE format('REVOKE ALL ON TABLE public.usuario, public.produto, public.loja,
            public.setor, public.notificacao, public.notificacao_lida, public.email_preference,
            public.email_token, public.email_delivery, public.job_state, public.external_lookup_cache,
            public.api_budget, public.movimento, public.audit_event, public.login_limit,
            public.alembic_version FROM %I', role_name);
          END IF;
        END LOOP; END $$""")


def downgrade():
    raise RuntimeError('Esta versão contém histórico operacional. Restaure um backup validado em outro banco para retornar.')
