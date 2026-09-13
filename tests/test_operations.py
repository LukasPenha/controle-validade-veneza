import unittest
from unittest.mock import patch, Mock
from decimal import Decimal
from datetime import timedelta
from flask import g
from sqlalchemy import text
import test_features as fixtures
from app import db, create_app
from app.models import Produto, Movimento, AuditEvent, LoginLimit, utcnow
from app.inventory import financial_data
from app.notifications import sync_expiry_notifications, unread_query
from tools.backup import check_target


class OperationTests(unittest.TestCase):
    setUp=fixtures.FeatureTests.setUp
    tearDown=fixtures.FeatureTests.tearDown
    login=fixtures.FeatureTests.login

    def movement(self, item, qty, kind='venda', key='a'*32, price='8.50'):
        return self.client.post(f'/lotes/{item.id}',data=dict(action='movement',quantidade=qty,
            tipo=kind,request_key=key,valor_unitario=price,motivo='Operação de teste'))

    def test_partial_moves_totals_and_replay(self):
        self.login()
        item=Produto.query.first()
        item.custo_unitario=Decimal('5.25')
        db.session.commit()
        self.movement(item,4)
        self.assertEqual(item.quantidade,6)
        self.movement(item,4)
        self.assertEqual((item.quantidade,Movimento.query.count()),(6,1))
        self.movement(item,7,key='b'*32)
        self.assertEqual(item.quantidade,6)
        self.movement(item,6,kind='descarte',key='c'*32)
        self.assertEqual(item.quantidade,0)
        self.assertEqual(Movimento.query.count(),2)
        sync_expiry_notifications()
        self.assertFalse(unread_query(self.user).filter_by(produto_id=item.id,kind='due_today').count())
        totals=financial_data(self.today.year,1,1)
        self.assertEqual(totals['venda']['value'],Decimal('34.00'))
        self.assertEqual(totals['descarte']['cost'],Decimal('31.50'))
        self.client.post(f'/lotes/{item.id}',data=dict(action='cost',custo_unitario='99.00'))
        self.assertEqual(Movimento.query.first().custo_unitario,Decimal('5.25'))
        self.assertEqual(financial_data(self.today.year,2,1)['venda']['units'],0)

    def test_scope_manual_and_audit(self):
        self.login()
        self.client.post('/lotes/novo',data=dict(manual='1',nome_produto='Pão da casa',
            quantidade='12',validade=str(self.today),custo_unitario='1.25',setor_id='2',loja_id='2'))
        item=Produto.query.order_by(Produto.id.desc()).first()
        self.assertEqual((item.source,item.barcode,item.setor_id,item.loja_id),('manual','',1,1))
        event=AuditEvent.query.filter_by(produto_id=item.id).first()
        self.assertEqual(event.actor,self.user.username)
        self.movement(item,2,kind='devolucao',price='1.10')
        event=AuditEvent.query.filter_by(produto_id=item.id).order_by(AuditEvent.id.desc()).first()
        self.assertEqual(event.changes['quantidade'],{'antes':'12','depois':'10'})
        foreign=Produto.query.filter_by(loja_id=2).first()
        self.assertEqual(self.client.get(f'/lotes/{foreign.id}').status_code,404)
        self.assertEqual(self.movement(foreign,1,key='b'*32).status_code,404)
        for page in ['/lotes','/historico',f'/lotes/{item.id}','/lotes/novo?manual=1']:
            self.assertEqual(self.client.get(page).status_code,200,page)

    def test_archive_preserves_records_and_history(self):
        self.login()
        item=Produto.query.first()
        self.client.post(f'/produtos/{item.id}/excluir')
        self.assertFalse(item.arquivado)
        self.movement(item,item.quantidade,kind='descarte')
        self.client.post(f'/produtos/{item.id}/excluir')
        self.assertTrue(item.arquivado)
        self.assertEqual(Movimento.query.count(),1)
        self.assertTrue(AuditEvent.query.filter_by(produto_id=item.id).count())
        totals=financial_data(self.today.year)
        self.assertEqual(totals['descarte']['missing_cost'],1)

    def test_login_limit_shared_and_expires(self):
        for _ in range(10):
            self.assertEqual(self.client.post('/login',data={'username':self.user.username,'password':'wrong'}).status_code,200)
        self.assertEqual(self.app.test_client().post('/login',data={'username':self.user.username.upper(),'password':'Original-12345'}).status_code,429)
        LoginLimit.query.update({'expires_at':utcnow()-timedelta(seconds=1)})
        db.session.commit()
        self.assertEqual(self.login().status_code,302)

    def test_invalid_money_does_not_mutate(self):
        self.login()
        item=Produto.query.first()
        for price in ['NaN','Infinity','-5','0.001']:
            self.movement(item,1,price=price)
        self.assertEqual(Movimento.query.count(),0)
        self.assertEqual(item.quantidade,10)


class GmailTests(unittest.TestCase):
    def test_success_and_ambiguous_delivery(self):
        from email.message import EmailMessage
        from app.gmail_transport import send_gmail
        import requests
        app=create_app({'TESTING':True,'SECRET_KEY':'gmail-tests-'*4,'SQLALCHEMY_DATABASE_URI':'sqlite://',
            'SCHEDULER_ENABLED':False,'GMAIL_CLIENT_ID':'test','GMAIL_CLIENT_SECRET':'test','GMAIL_REFRESH_TOKEN':'test'})
        message=EmailMessage()
        message['To']='example@example.test'
        message.set_content('Teste')
        token=Mock(status_code=200)
        token.json.return_value={'access_token':'test-access'}
        sent=Mock(status_code=200)
        sent.json.return_value={'id':'test-id'}
        with app.app_context():
            with patch('app.gmail_transport.requests.post',side_effect=[token,sent]) as post:
                send_gmail(message)
                self.assertIn('raw',post.call_args.kwargs['json'])
            with patch('app.gmail_transport.requests.post',side_effect=[token,requests.Timeout]):
                with self.assertRaises(TimeoutError): send_gmail(message)
            with patch('app.gmail_transport.requests.post',side_effect=requests.Timeout):
                with self.assertRaises(ValueError): send_gmail(message)


class BackupTests(unittest.TestCase):
    def test_restore_target_is_local_and_distinct(self):
        source='postgresql://test:test@db.example/source'
        for target in [source,'postgresql://test:test@db.example/veneza_restore','postgresql://test:test@localhost/production']:
            with self.assertRaises(ValueError): check_target(source,target)
        check_target(source,'postgresql://test:test@127.0.0.1/veneza_restore')


class UpgradeTests(unittest.TestCase):
    def test_upgrade_preserves_existing_lot(self):
        from flask_migrate import upgrade
        app=create_app({'TESTING':True,'SECRET_KEY':'upgrade-tests-'*4,'SQLALCHEMY_DATABASE_URI':'sqlite://','SCHEDULER_ENABLED':False})
        with app.app_context():
            upgrade(revision='20260909_v2')
            db.session.execute(text("INSERT INTO loja (id,nome) VALUES (1,'Loja')"))
            db.session.execute(text("INSERT INTO setor (id,nome) VALUES (1,'Setor existente')"))
            db.session.execute(text("""INSERT INTO produto
                (nome_produto,barcode,plu,source,source_url,marca,lote,quantidade,validade,status,data_cadastro,loja_id,setor_id)
                VALUES ('Legado','3017620422003','','openfoodfacts','','','',10,'2026-12-01','Para Rebaixa','2026-09-09',1,1)"""))
            db.session.commit()
            upgrade()
            item=Produto.query.one()
            self.assertEqual((item.nome_produto,item.quantidade,item.custo_unitario,item.arquivado),('Legado',10,None,False))
            db.session.remove()
            db.engine.dispose()
