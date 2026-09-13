"""Preenche setores iniciais inclusive quando o administrador foi criado por SQL."""
from alembic import op
import sqlalchemy as sa

revision = '20260909_setores'
down_revision = '20260909_v2'
branch_labels = None
depends_on = None


def upgrade():
    for name in ('Padaria', 'Açougue', 'Mercearia', 'Frios', 'Bebidas', 'Higiene e limpeza'):
        op.get_bind().execute(sa.text(
            'INSERT INTO setor (nome) VALUES (:name) ON CONFLICT (nome) DO NOTHING'
        ), {'name': name})


def downgrade():
    # Setores podem ter usuários/lotes vinculados; mantenha os dados operacionais.
    pass
