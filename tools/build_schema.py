"""Gera os artefatos SQL sem reescrever migrações já publicadas."""
from pathlib import Path
import importlib.util
import io
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_mock_engine
from alembic.migration import MigrationContext
from alembic.operations import Operations
from app import create_app, db

root=Path(__file__).resolve().parents[1]
app=create_app({'TESTING':True,'SECRET_KEY':'schema-local-'*4,'SQLALCHEMY_DATABASE_URI':'sqlite://','SCHEDULER_ENABLED':False})
with app.app_context():
    statements=[]
    engine=create_mock_engine('postgresql://',lambda statement,*a,**k:statements.append(str(statement.compile(dialect=engine.dialect)).strip()+';'))
    db.metadata.create_all(engine,checkfirst=False)
    seed=(root/'database/cadastrar_setores.sql').read_text(encoding='utf-8')
    sql='-- INSTALAÇÃO NOVA. Não execute no banco existente.\nBEGIN;\n\n'+'\n\n'.join(statements)+'\n'+seed
    sql+="\nCREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY);\nINSERT INTO alembic_version VALUES ('20260912_operacao');\n"
    output=io.StringIO()
    context=MigrationContext.configure(dialect_name='postgresql',dialect_opts={'paramstyle':'named'},opts={'as_sql':True,'output_buffer':output})
    with Operations.context(context):
        spec=importlib.util.spec_from_file_location('upgrade_operations',root/'migrations/versions/20260912_operacao.py')
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.upgrade()
    ddl=output.getvalue()
    # Reuse only the role restriction for a fresh schema.
    sql+=ddl[ddl.index('DO $$'):]+'\nCOMMIT;\n'
    (root/'database/novo_banco.sql').write_text('\n'.join(line.rstrip() for line in sql.splitlines())+'\n',encoding='utf-8')
    guard="""DO $$ BEGIN
IF NOT EXISTS (SELECT 1 FROM public.alembic_version WHERE version_num IN ('20260909_v2','20260909_setores')) THEN
RAISE EXCEPTION 'Versão diferente da esperada. Não reaplique a atualização.';
END IF; END $$;
"""
    legacy_seed=seed.replace("VALUES ('Padaria'), ('Açougue'), ('Mercearia'), ('Frios')", "VALUES ('Padaria'), ('Açougue'), ('Mercearia'), ('Frios'),\n       ('Bebidas'), ('Higiene e limpeza')")
    upgrade='-- ATUALIZAÇÃO DO BANCO EXISTENTE, SEM APAGAR LOTES OU USUÁRIOS.\nBEGIN;\nSET LOCAL search_path TO public;\n'+guard+legacy_seed+'\n'+ddl
    upgrade+="UPDATE alembic_version SET version_num='20260912_operacao';\nCOMMIT;\n"
    (root/'database/atualizar_20260912.sql').write_text('\n'.join(line.rstrip() for line in upgrade.splitlines())+'\n',encoding='utf-8')
    photo_output=io.StringIO()
    photo_context=MigrationContext.configure(dialect_name='postgresql',dialect_opts={'paramstyle':'named'},opts={'as_sql':True,'output_buffer':photo_output})
    with Operations.context(photo_context):
        spec=importlib.util.spec_from_file_location('upgrade_exposure',root/'migrations/versions/20260913_exposicao.py')
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.upgrade()
    photo_ddl=photo_output.getvalue()
    photo_guard=guard.replace("version_num IN ('20260909_v2','20260909_setores')", "version_num='20260912_operacao'")
    photo_sql='-- ATUALIZAÇÃO: FOTOS DA EXPOSIÇÃO. Execute após atualizar_20260912.sql.\nBEGIN;\nSET LOCAL search_path TO public;\n'+photo_guard+photo_ddl+"UPDATE alembic_version SET version_num='20260913_exposicao';\nCOMMIT;\n"
    (root/'database/atualizar_20260913.sql').write_text(photo_sql,encoding='utf-8')
    sql=sql.replace("VALUES ('20260912_operacao')", "VALUES ('20260913_exposicao')")
    sql=sql.replace('\nCOMMIT;', '\n'+photo_ddl[photo_ddl.index('DO $$'):]+'\nCOMMIT;')
    (root/'database/novo_banco.sql').write_text('\n'.join(line.rstrip() for line in sql.splitlines())+'\n',encoding='utf-8')
    sector_output=io.StringIO()
    sector_context=MigrationContext.configure(dialect_name='postgresql',dialect_opts={'paramstyle':'named'},opts={'as_sql':True,'output_buffer':sector_output})
    with Operations.context(sector_context):
        spec=importlib.util.spec_from_file_location('upgrade_sectors',root/'migrations/versions/20260916_mercearia.py')
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.upgrade()
    sector_guard=guard.replace("version_num IN ('20260909_v2','20260909_setores')", "version_num='20260913_exposicao'")
    sector_sql='-- UNIÃO DOS SETORES EM MERCEARIA, PRESERVANDO OS REGISTROS.\nBEGIN;\nSET LOCAL search_path TO public;\n'+sector_guard+sector_output.getvalue()+"UPDATE alembic_version SET version_num='20260916_mercearia';\nCOMMIT;\n"
    (root/'database/atualizar_20260916.sql').write_text(sector_sql,encoding='utf-8')
    sql=sql.replace("VALUES ('20260913_exposicao')", "VALUES ('20260916_mercearia')")
    (root/'database/novo_banco.sql').write_text('\n'.join(line.rstrip() for line in sql.splitlines())+'\n',encoding='utf-8')
    db.engine.dispose()
print('SQL de instalação e atualização gerados; migrações existentes preservadas.')
