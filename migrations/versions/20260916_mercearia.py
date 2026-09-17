"""Reúne Bebidas e Higiene e Limpeza no setor Mercearia."""
from alembic import op

revision = '20260916_mercearia'
down_revision = '20260913_exposicao'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("INSERT INTO setor (nome) VALUES ('Mercearia') ON CONFLICT (nome) DO NOTHING")
    source = "SELECT id FROM setor WHERE lower(trim(nome)) IN ('bebidas','higiene e limpeza')"
    target = "SELECT id FROM setor WHERE nome='Mercearia'"
    # Preserve the records and scope of their history before removing obsolete sectors.
    op.execute(f"UPDATE produto SET setor_id=({target}), exposure_revision=exposure_revision+1 WHERE setor_id IN ({source})")
    for table in ('usuario', 'notificacao', 'audit_event'):
        op.execute(f"UPDATE {table} SET setor_id=({target}) WHERE setor_id IN ({source})")
    op.execute(f"DELETE FROM setor WHERE id IN ({source})")


def downgrade():
    raise RuntimeError('A união dos setores não pode ser desfeita sem consultar o backup anterior.')
