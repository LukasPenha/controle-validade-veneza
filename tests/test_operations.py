import unittest
from unittest.mock import patch, Mock
from decimal import Decimal
from datetime import timedelta
from flask import g
from sqlalchemy import text
import test_features as fixtures
from app import db, create_app
from app.models import Produto, Movimento, AuditEvent, LoginLimit, utcnow
from app.models import ExposureProof
from app.inventory import normalize_photo
from PIL import Image
import io
from app.notifications import sync_expiry_notifications, unread_query
from tools.backup import check_target, run


class OperationTests(unittest.TestCase):
    setUp=fixtures.FeatureTests.setUp
    tearDown=fixtures.FeatureTests.tearDown
    login=fixtures.FeatureTests.login

    def photo(self, item, content=None, revision=None):
        if content is None:
            stream=io.BytesIO()
            Image.new('RGB',(80,60),'red').save(stream,format='PNG')
            content=stream.getvalue()
        return self.client.post(f'/produtos/{item.id}/exposicao',data={
            'foto':(io.BytesIO(content),'foto.png'),'observacao':'Ponta da gôndola',
            'revision':item.exposure_revision if revision is None else revision})

    def test_photo_scope_duplicates_and_invalidation(self):
        self.login()
        item=Produto.query.first()
        item.status='Em Rebaixa'
        db.session.commit()
        revision=item.exposure_revision
        self.assertEqual(self.photo(item).status_code,302)
        proof=ExposureProof.query.one()
        self.assertEqual(proof.actor,self.user.username)
        self.assertTrue(proof.image_data.startswith(b'\xff\xd8'))
        self.assertEqual(self.client.get(f'/exposicoes/{proof.id}/foto').status_code,200)
        self.photo(item)
        self.assertEqual(ExposureProof.query.count(),1)
        item.quantidade+=1
        db.session.commit()
        self.assertGreater(item.exposure_revision,revision)
        self.photo(item,revision=revision)
        self.assertEqual(ExposureProof.query.count(),1)
        self.photo(item)
        self.assertEqual(ExposureProof.query.count(),2)
        foreign=Produto.query.filter_by(loja_id=2).first()
        self.assertEqual(self.photo(foreign).status_code,404)
        self.user.loja_id=2
        db.session.commit()
        self.assertEqual(self.client.get(f'/exposicoes/{proof.id}/foto').status_code,404)

    def test_photo_invalid_state_file_and_role(self):
        self.login()
        item=Produto.query.first()
        self.photo(item)
        self.assertEqual(ExposureProof.query.count(),0)
        item.status='Em Rebaixa'
        db.session.commit()
        self.photo(item,content=b'<script>invalid</script>')
        self.assertEqual(ExposureProof.query.count(),0)
        self.user.role='gerente'
        db.session.commit()
        self.assertEqual(self.photo(item).status_code,403)

    def test_product_form_no_batch_or_cost_and_scoped_manual(self):
        self.login()
        self.client.post('/produtos/novo',data=dict(manual='1',nome_produto='Pão da casa',
            quantidade='12',validade=str(self.today),lote='ignored',custo_unitario='1.25',setor_id='2',loja_id='2',plu='123'))
        item=Produto.query.order_by(Produto.id.desc()).first()
        self.assertEqual((item.source,item.barcode,item.setor_id,item.loja_id,item.plu),('manual','',1,1,'123'))
        self.assertFalse(item.lote)
        self.assertIsNone(item.custo_unitario)
        for page in ['/produtos','/historico',f'/produtos/{item.id}','/produtos/novo?manual=1']:
            response=self.client.get(page)
            self.assertEqual(response.status_code,200,page)
            self.assertNotIn('name="lote"',response.text)
            self.assertNotIn('name="custo_unitario"',response.text)
        self.assertEqual(self.client.post(f'/lotes/{item.id}',data={'action':'movement'}).status_code,405)

    def test_close_requires_proof_and_keeps_history(self):
        self.login()
        item=Produto.query.first()
        self.client.post(f'/produtos/{item.id}/encerrar',data={'motivo':'Trabalho concluído'})
        self.assertFalse(item.arquivado)
        item.status='Em Rebaixa'
        db.session.commit()
        self.photo(item)
        self.client.post(f'/produtos/{item.id}/encerrar',data={'motivo':'Trabalho concluído'})
        self.assertTrue(item.arquivado)
        self.assertEqual(ExposureProof.query.count(),1)
        self.assertTrue(AuditEvent.query.filter_by(produto_id=item.id,action='encerramento').count())

    def test_login_limit_shared_and_expires(self):
        for _ in range(10):
            self.assertEqual(self.client.post('/login',data={'username':self.user.username,'password':'wrong'}).status_code,200)
        self.assertEqual(self.app.test_client().post('/login',data={'username':self.user.username.upper(),'password':'Original-12345'}).status_code,429)
        LoginLimit.query.update({'expires_at':utcnow()-timedelta(seconds=1)})
        db.session.commit()
        self.assertEqual(self.login().status_code,302)

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
    def test_failure_diagnostics_do_not_expose_private_stderr(self):
        result=Mock(returncode=1,stdout=b'',stderr=b'password authentication failed: private-user private-password')
        with patch('tools.backup.subprocess.run',return_value=result):
            with self.assertRaises(RuntimeError) as error:
                run(['docker'],label='pg_dump')
        self.assertIn('pg_dump',str(error.exception))
        self.assertIn('Autenticação',str(error.exception))
        self.assertNotIn('private',str(error.exception))

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
