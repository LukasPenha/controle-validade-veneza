"""Integration checks against disposable CI PostgreSQL only."""
import os
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import psycopg2
from sqlalchemy.engine import make_url
from sqlalchemy import text
from flask_migrate import upgrade
from app import create_app, db
from app.models import Produto, Usuario, Movimento

uri=os.environ['DATABASE_URL']
url=make_url(uri)
assert url.host in ('127.0.0.1','localhost') and url.database=='veneza_source', 'Only isolated CI database allowed'
app=create_app({'TESTING':True,'SECRET_KEY':'postgres-ci-only-'*4,'SQLALCHEMY_DATABASE_URI':uri,
    'SCHEDULER_ENABLED':False,'WTF_CSRF_ENABLED':False,'SESSION_COOKIE_SECURE':False})
with app.app_context():
    upgrade(revision='20260909_v2')
    db.session.execute(text('CREATE ROLE anon'))
    db.session.execute(text('CREATE ROLE authenticated'))
    db.session.execute(text("INSERT INTO loja (nome) VALUES ('Teste')"))
    db.session.execute(text("INSERT INTO setor (nome) VALUES ('Mercearia')"))
    db.session.execute(text("""INSERT INTO produto (nome_produto,barcode,plu,source,source_url,marca,lote,quantidade,validade,status,data_cadastro,loja_id,setor_id)
        VALUES ('Teste','3017620422003','','openfoodfacts','','','',10,'2026-12-01','Para Rebaixa',now(),1,1)"""))
    db.session.commit()
    # Exercise the exact SQL delivered to the user, not only Alembic's Python path.
    raw=db.engine.raw_connection()
    with raw.cursor() as cursor:
        cursor.execute(Path('database/atualizar_20260912.sql').read_text(encoding='utf-8'))
    raw.commit()
    raw.close()
    item=Produto.query.one()
    assert item.quantidade==10 and item.custo_unitario is None
    user=Usuario(username='ci@example.test',role='gerente',loja_id=1)
    user.set_password('Test-only-password')
    db.session.add(user)
    db.session.commit()
    identity=user.get_id()
    item_id=item.id

def submit(key):
    client=app.test_client()
    with client.session_transaction() as session:
        session['_user_id']=identity
        session['_fresh']=True
    return client.post(f'/lotes/{item_id}',data=dict(action='movement',request_key=key,quantidade=7,
        tipo='venda',valor_unitario='2.50',motivo='Concurrent test')).status_code

with ThreadPoolExecutor(max_workers=2) as pool:
    assert list(pool.map(submit,['a'*32,'b'*32])) == [302,302]
with app.app_context():
    db.session.expire_all()
    assert db.session.get(Produto,item_id).quantidade==3
    assert Movimento.query.count()==1
    db.session.remove()
    db.engine.dispose()
connection=psycopg2.connect(uri)
connection.autocommit=True
with connection.cursor() as cursor:
    cursor.execute('CREATE DATABASE veneza_restore')
    cursor.execute('CREATE DATABASE veneza_fresh')
connection.close()
fresh=psycopg2.connect(url.set(database='veneza_fresh').render_as_string(hide_password=False))
with fresh.cursor() as cursor:
    cursor.execute(Path('database/novo_banco.sql').read_text(encoding='utf-8'))
    cursor.execute('SELECT count(*) FROM setor')
    assert cursor.fetchone()[0]==6
fresh.commit()
fresh.close()
print('PostgreSQL: atualização preservou lote, instalação vazia validada e baixa concorrente respeitou saldo.')
