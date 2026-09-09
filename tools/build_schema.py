"""Gera SQL e migração para banco vazio; nunca acessa o banco de produção."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_mock_engine
from alembic.migration import MigrationContext
from alembic.autogenerate import produce_migrations, render_python_code
from app import create_app, db
from app.models import UTCDateTime

app = create_app({'TESTING': True, 'SECRET_KEY': 'schema-generator-local-' * 3,
                  'SQLALCHEMY_DATABASE_URI': 'sqlite://', 'SCHEDULER_ENABLED': False})
root = Path(__file__).resolve().parents[1]
with app.app_context():
    statements = []
    engine = create_mock_engine('postgresql://', lambda statement, *a, **k:
        statements.append(str(statement.compile(dialect=engine.dialect)).strip() + ';'))
    db.metadata.create_all(engine, checkfirst=False)
    sql = '-- NOVO BANCO VENEZA V2. Execute somente em um banco vazio.\nBEGIN;\n\n'
    sql += '\n\n'.join(statements)
    sql += "\n\nCREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY);\n"
    sql += "INSERT INTO alembic_version VALUES ('20260909_v2');\nCOMMIT;\n"
    (root / 'database').mkdir(exist_ok=True)
    (root / 'database' / 'novo_banco.sql').write_text(sql, encoding='utf-8')
    with db.engine.connect() as connection:
        context = MigrationContext.configure(connection)
        operations = produce_migrations(context, db.metadata)
        def render_item(kind, item, autogen_context):
            if kind == 'type' and isinstance(item, UTCDateTime):
                return 'sa.DateTime(timezone=True)'
            return False
        upgrade = render_python_code(operations.upgrade_ops, render_item=render_item)
        if "uq_usuario_username_lower" not in upgrade:
            upgrade += "\n    op.create_index('uq_usuario_username_lower', 'usuario', [sa.text('lower(username)')], unique=True)"
        downgrade = render_python_code(operations.downgrade_ops, render_item=render_item)
        module = ('"""Instalação V2 em banco vazio."""\nfrom alembic import op\nimport sqlalchemy as sa\n\n'
                  "revision = '20260909_v2'\ndown_revision = None\nbranch_labels = None\ndepends_on = None\n\n"
                  'def upgrade():\n' + upgrade + '\n\ndef downgrade():\n' + downgrade + '\n')
        (root / 'migrations' / 'versions' / '20260909_v2.py').write_text(module, encoding='utf-8')
    db.engine.dispose()
print('SQL PostgreSQL e migração inicial gerados.')
