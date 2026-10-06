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

    def test_ip_limit_blocks_attacker_without_locking_owner(self):
        self.app.config['LOGIN_IP_LIMIT_ENABLED']=True
        attacker=self.app.test_client()
        for _ in range(20):
            attacker.post('/login',data={'username':self.user.username,'password':'wrong'},environ_base={'REMOTE_ADDR':'203.0.113.9'})
        self.assertEqual(attacker.post('/login',data={'username':self.user.username,'password':'wrong'},environ_base={'REMOTE_ADDR':'203.0.113.9'}).status_code,429)
        owner=self.app.test_client().post('/login',data={'username':self.user.username,'password':'Original-12345'},environ_base={'REMOTE_ADDR':'198.51.100.7'})
        self.assertEqual(owner.status_code,302)

    def test_reports_keep_products_without_creator(self):
        self.login()
        hoje=self.today.isoformat()
        with patch('app.routes.draw_pdf_report') as draw:
            self.assertEqual(self.client.get(f'/encarregado/relatorio/pdf?data_inicio={hoje}&data_fim={hoje}').status_code,200)
        rows=draw.call_args.args[3]
        self.assertEqual(len(rows),Produto.query.filter_by(loja_id=1,setor_id=1).count())
        self.assertTrue(all(row['criado_por']=='Excluído' for row in rows))
        self.user.role='gerente'
        db.session.commit()
        with patch('app.routes.draw_pdf_report') as draw:
            self.assertEqual(self.client.get(f'/gerente/relatorio/pdf?data_inicio={hoje}&data_fim={hoje}').status_code,200)
        self.assertEqual(len(draw.call_args.args[3]),Produto.query.filter_by(loja_id=1).count())

    def test_reset_link_config_error_is_logged(self):
        self.app.config['PUBLIC_BASE_URL']='http://sem-https.test'
        with self.assertLogs(self.app.logger,level='ERROR') as logs:
            response=self.client.post('/esqueci-senha',data={'email':self.user.username})
        self.assertEqual(response.status_code,302)
        self.assertIn('redefinição de senha',logs.output[0])

    def test_proxy_fix_uses_forwarded_ip(self):
        app=create_app({'TESTING':True,'SECRET_KEY':'proxy-tests-'*4,'SQLALCHEMY_DATABASE_URI':'sqlite://',
                        'SCHEDULER_ENABLED':False,'TRUSTED_PROXIES':1})
        @app.route('/_ip')
        def _ip():
            from flask import request
            return request.remote_addr
        response=app.test_client().get('/_ip',headers={'X-Forwarded-For':'203.0.113.9'},environ_base={'REMOTE_ADDR':'10.0.0.1'})
        self.assertEqual(response.get_data(as_text=True),'203.0.113.9')

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
    def test_migrations_match_models(self):
        from flask_migrate import upgrade
        from alembic.autogenerate import compare_metadata
        from alembic.migration import MigrationContext
        app=create_app({'TESTING':True,'SECRET_KEY':'schema-tests-'*4,'SQLALCHEMY_DATABASE_URI':'sqlite://','SCHEDULER_ENABLED':False})
        with app.app_context():
            upgrade()
            differences=compare_metadata(MigrationContext.configure(db.session.connection()),db.metadata)
            self.assertEqual(differences,[])
            db.session.remove()
            db.engine.dispose()

    def test_sector_merge_preserves_users_products_notifications_and_history(self):
        from flask_migrate import upgrade
        from app.models import Setor, Loja, Usuario, Notificacao
        app=create_app({'TESTING':True,'SECRET_KEY':'merge-tests-'*4,'SQLALCHEMY_DATABASE_URI':'sqlite://','SCHEDULER_ENABLED':False})
        with app.app_context():
            upgrade(revision='20260913_exposicao')
            store=Loja(nome='Teste')
            db.session.add(store)
            db.session.flush()
            beverages=Setor.query.filter_by(nome='Bebidas').one()
            hygiene=Setor.query.filter_by(nome='Higiene e limpeza').one()
            user=Usuario(username='merge@example.test',password_hash='test',role='encarregado_setor',loja_id=store.id,setor_id=hygiene.id)
            item=Produto(nome_produto='Suco',barcode='',source='manual',source_url='',quantidade=5,validade=utcnow().date(),loja_id=store.id,setor_id=beverages.id)
            db.session.add_all([user,item])
            db.session.flush()
            notification=Notificacao(produto_id=item.id,loja_id=store.id,setor_id=beverages.id,event_key='merge-test',kind='created',severity='info',mensagem='Teste')
            db.session.add(notification)
            db.session.commit()
            product_id=item.id
            user_id=user.id
            db.session.remove()
            upgrade()
            grocery=Setor.query.filter_by(nome='Mercearia').one()
            self.assertEqual(Setor.query.count(),4)
            self.assertEqual(db.session.get(Produto,product_id).setor_id,grocery.id)
            self.assertEqual(db.session.get(Usuario,user_id).setor_id,grocery.id)
            self.assertEqual(Notificacao.query.one().setor_id,grocery.id)
            self.assertEqual(AuditEvent.query.filter_by(produto_id=product_id).first().setor_id,grocery.id)
            self.assertEqual(db.session.get(Produto,product_id).quantidade,5)
            upgrade()
            self.assertEqual(Setor.query.count(),4)
            db.session.remove()
            db.engine.dispose()

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


class InputValidationTests(unittest.TestCase):
    setUp=fixtures.FeatureTests.setUp
    tearDown=fixtures.FeatureTests.tearDown
    login=fixtures.FeatureTests.login

    def as_role(self, role):
        self.user.role=role
        if role in ('gerente_geral','gerente_trocas'):
            self.user.loja_id=self.user.setor_id=None
        db.session.commit()
        self.login()

    def test_bad_report_inputs_do_not_crash(self):
        self.as_role('gerente')
        for query in ['data_inicio=abc&data_fim=2026-01-01','data_inicio=2026-02-01&data_fim=2026-01-01',
                      'data_inicio=2024-01-01&data_fim=2026-01-01','']:
            self.assertEqual(self.client.get('/gerente/relatorio/pdf?'+query).status_code,302,query)
        self.as_role('gerente_geral')
        for query in ['data_inicio=abc&data_fim=x','search_term=a&loja_id=999','search_term=a&loja_id=abc',
                      'data_inicio=2024-01-01&data_fim=2026-01-01']:
            self.assertEqual(self.client.get('/relatorio/pdf?'+query).status_code,302,query)
        self.assertEqual(self.client.get('/gerente-geral/usuarios?loja_id=abc').status_code,200)

    def test_general_report_has_row_limit(self):
        self.as_role('gerente_geral')
        with patch('app.routes.MAX_REPORT_ROWS',2), patch('app.routes.draw_pdf_report') as draw:
            self.assertEqual(self.client.get('/relatorio/pdf?search_term=a').status_code,302)
            draw.assert_not_called()
        with patch('app.routes.draw_pdf_report') as draw:
            self.assertEqual(self.client.get('/relatorio/pdf?search_term=Arroz&loja_id=1').status_code,200)
        self.assertEqual(len(draw.call_args.args[3]),2)

    def test_store_edit_rejects_empty_and_duplicate_names(self):
        from app.models import Loja
        self.as_role('gerente_geral')
        self.client.post('/gerente-geral/loja/editar/1',data={'nome':''})
        self.client.post('/gerente-geral/loja/editar/1',data={'nome':'b'})
        self.client.post('/gerente-geral/lojas',data={'nome':'  '})
        db.session.expire_all()
        self.assertEqual(db.session.get(Loja,1).nome,'A')
        self.assertEqual(Loja.query.count(),2)
        self.client.post('/gerente-geral/loja/editar/1',data={'nome':'Centro','estado':'sp'})
        db.session.expire_all()
        self.assertEqual((db.session.get(Loja,1).nome,db.session.get(Loja,1).estado),('Centro','SP'))

    def test_general_report_keeps_products_without_store_user(self):
        self.as_role('gerente_geral')
        Produto.query.update({'criado_por_id':self.user.id})
        db.session.commit()
        with patch('app.routes.draw_pdf_report') as draw:
            self.client.get('/relatorio/pdf?search_term=Arroz')
        self.assertEqual(len(draw.call_args.args[3]),2)


class SyncPerformanceTests(unittest.TestCase):
    setUp=fixtures.FeatureTests.setUp
    tearDown=fixtures.FeatureTests.tearDown

    def count_queries(self, func):
        from sqlalchemy import event
        statements=[]
        listener=lambda *args: statements.append(args[2])
        event.listen(db.engine,'before_cursor_execute',listener)
        try:
            func()
        finally:
            event.remove(db.engine,'before_cursor_execute',listener)
        return len(statements)

    def test_full_sync_query_count_does_not_grow_with_products(self):
        sync_expiry_notifications()
        small=self.count_queries(sync_expiry_notifications)
        base=Produto.query.first()
        for i in range(60):
            db.session.add(Produto(nome_produto=f'Extra {i}',plu='',barcode=base.barcode,source_url=base.source_url,
                loja_id=1,setor_id=1,quantidade=1,validade=base.validade))
        db.session.commit()
        sync_expiry_notifications()
        self.assertEqual(self.count_queries(sync_expiry_notifications),small)

    def test_product_sync_replaces_old_alert(self):
        from app.notifications import sync_product_notifications
        from app.models import Notificacao
        item=Produto.query.filter_by(nome_produto='Vencido').one()
        sync_product_notifications(item)
        old=Notificacao.query.filter_by(produto_id=item.id,resolved_at=None).one()
        item.validade=self.today+timedelta(days=3)
        db.session.commit()
        sync_product_notifications(item)
        db.session.refresh(old)
        self.assertIsNotNone(old.resolved_at)
        self.assertEqual(Notificacao.query.filter_by(produto_id=item.id,resolved_at=None).one().kind,'approaching')


class EmailFailureAndRetentionTests(unittest.TestCase):
    setUp=fixtures.FeatureTests.setUp
    tearDown=fixtures.FeatureTests.tearDown
    login=fixtures.FeatureTests.login
    preference=fixtures.FeatureTests.preference
    photo=OperationTests.photo

    def queue_reset(self, key):
        from app.email_models import EmailDelivery
        db.session.add(EmailDelivery(delivery_key=key,user_id=self.user.id,kind='reset',
            recipient=self.user.username,subject='Redefina sua senha',body='x'))
        db.session.commit()

    def test_gmail_failures_are_recorded_and_shown_to_general_manager(self):
        from app.models import JobState
        from app.preferences import process_email_jobs
        self.app.config.update(MAIL_SERVER='smtp.test',MAIL_DEFAULT_SENDER='a@example.test')
        with patch('app.mail_service.send_message',side_effect=ValueError('Não foi possível autorizar o Gmail.')):
            for i in range(3):
                self.queue_reset(f'reset-{i}')
                process_email_jobs(self.app)
        state=db.session.get(JobState,'email')
        self.assertEqual(state.failures,3)
        self.assertIsNone(state.last_success_at)
        self.assertIn('autorizar o Gmail',state.last_error)
        self.user.role='gerente_geral'; self.user.loja_id=self.user.setor_id=None
        db.session.commit()
        self.login()
        self.assertIn('não estão saindo',self.client.get('/gerente-geral/dashboard').text)
        with patch('app.mail_service.send_message'):
            self.queue_reset('reset-ok')
            process_email_jobs(self.app)
        db.session.refresh(state)
        self.assertEqual((state.failures,state.last_error),(0,None))
        self.assertIsNotNone(state.last_success_at)

    def test_retention_resolves_and_purges_old_records(self):
        from app.models import Notificacao, NotificationRead
        from app.email_models import EmailDelivery
        from app.retention import purge_old_data, purge_if_due
        item=Produto.query.first()
        now=utcnow()
        old_info=Notificacao(event_key='created:old',produto_id=item.id,loja_id=1,setor_id=1,kind='created',
            severity='info',mensagem='antigo',timestamp=now-timedelta(days=40))
        recent_info=Notificacao(event_key='created:new',produto_id=item.id,loja_id=1,setor_id=1,kind='created',
            severity='info',mensagem='novo',timestamp=now-timedelta(days=2))
        ancient=Notificacao(event_key='created:ancient',produto_id=item.id,loja_id=1,setor_id=1,kind='created',
            severity='info',mensagem='muito antigo',timestamp=now-timedelta(days=400),resolved_at=now-timedelta(days=200))
        db.session.add_all([old_info,recent_info,ancient])
        db.session.flush()
        db.session.add(NotificationRead(usuario_id=self.user.id,notificacao_id=ancient.id))
        db.session.add(EmailDelivery(delivery_key='old-sent',user_id=self.user.id,kind='reset',recipient='x@example.test',
            subject='s',body='',status='sent',created_at=now-timedelta(days=100)))
        db.session.commit()
        counts=purge_old_data(now)
        self.assertEqual((counts['avisos_encerrados'],counts['avisos_apagados'],counts['emails_apagados']),(1,1,1))
        self.assertIsNotNone(db.session.get(Notificacao,old_info.id).resolved_at)
        self.assertIsNone(db.session.get(Notificacao,recent_info.id).resolved_at)
        self.assertEqual(NotificationRead.query.count(),0)
        self.assertIsNotNone(purge_if_due(now))
        self.assertIsNone(purge_if_due(now+timedelta(hours=1)))

    def test_purge_photos_needs_confirmation(self):
        self.login()
        item=Produto.query.first()
        item.status='Em Rebaixa'
        db.session.commit()
        self.photo(item)
        ExposureProof.query.update({'timestamp':utcnow()-timedelta(days=200)})
        item.arquivado=True
        db.session.commit()
        runner=self.app.test_cli_runner()
        self.assertIn('1 fotos seriam apagadas',runner.invoke(args=['purge-photos']).output)
        self.assertEqual(ExposureProof.query.count(),1)
        self.assertIn('1 fotos apagadas',runner.invoke(args=['purge-photos','--confirmar']).output)
        self.assertEqual(ExposureProof.query.count(),0)
