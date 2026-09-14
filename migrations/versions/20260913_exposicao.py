"""Fotos privadas da exposição por produto e revisão dos dados."""
from alembic import op
import sqlalchemy as sa

revision = '20260913_exposicao'
down_revision = '20260912_operacao'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('produto', sa.Column('exposure_revision', sa.Integer(), nullable=False, server_default='1'))
    op.create_table('exposure_proof',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('produto_id', sa.Integer(), sa.ForeignKey('produto.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('actor', sa.String(254), nullable=False),
        sa.Column('note', sa.String(255), nullable=False),
        sa.Column('quantidade', sa.Integer(), nullable=False),
        sa.Column('validade', sa.Date(), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('image_sha', sa.String(64), nullable=False),
        sa.Column('image_data', sa.LargeBinary(), nullable=False),
        sa.UniqueConstraint('produto_id','revision','image_sha',name='uq_exposure_image'),
        sa.CheckConstraint('length(image_data) <= 524288',name='ck_exposure_size'))
    op.create_index('ix_exposure_current','exposure_proof',['produto_id','revision'])
    if op.get_bind().dialect.name == 'postgresql':
        op.execute("""DO $$ DECLARE role_name text; BEGIN
        FOREACH role_name IN ARRAY ARRAY['anon','authenticated'] LOOP
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname=role_name) THEN
            EXECUTE format('REVOKE ALL ON TABLE public.exposure_proof FROM %I', role_name);
          END IF;
        END LOOP; END $$""")


def downgrade():
    raise RuntimeError('As fotos fazem parte do histórico. Restaure um backup para retornar.')
