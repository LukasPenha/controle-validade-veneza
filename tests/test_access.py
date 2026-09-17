import unittest
from unittest.mock import patch
from datetime import timedelta
from flask import template_rendered
import test_features as fixtures
from app import db
from app.models import Produto, agora_brasil, utcnow
from app.email_models import EmailDelivery
from app.mail_service import queue_due_alerts, deliver_pending
from app.notifications import sync_expiry_notifications, unread_query


class AccessTests(unittest.TestCase):
    setUp = fixtures.FeatureTests.setUp
    tearDown = fixtures.FeatureTests.tearDown
    login = fixtures.FeatureTests.login
    preference = fixtures.FeatureTests.preference

    def use_role(self, role):
        self.user.role = role
        db.session.commit()
        self.login()

    def test_general_and_auxiliary_direct_access(self):
        self.use_role('gerente_geral')
        for path in ['/produtos','/lotes','/produtos/novo?manual=1','/datas-curtas','/historico','/notifications']:
            self.assertEqual(self.client.get(path).status_code,403,path)
        self.assertEqual(self.client.post('/produtos/1/encerrar',data={'motivo':'teste'}).status_code,403)
        for path in ['/validades-proximas','/gerente-geral/dashboard','/gerente-geral/lojas','/gerente-geral/usuarios','/gerente-geral/relatorio','/perfil']:
            self.assertEqual(self.client.get(path).status_code,200,path)
        self.use_role('auxiliar_gestao')
        for path in ['/perfil','/historico','/produtos','/produtos/1','/gerente-geral/usuarios','/relatorio/pdf']:
            self.assertEqual(self.client.get(path).status_code,403,path)
        for path in ['/validades-proximas','/datas-curtas','/notifications','/produtos/novo?manual=1']:
            self.assertEqual(self.client.get(path).status_code,200,path)
        self.assertTrue(self.client.get('/').location.endswith('/validades-proximas'))
        self.assertFalse(db.session.get(Produto,1).arquivado)

    def test_trade_filters_all_stores_and_old_expired(self):
        self.use_role('gerente_trocas')
        captured=[]
        def capture(sender,template,context,**extra): captured.append(context)
        with template_rendered.connected_to(capture,self.app):
            self.client.get('/validades-proximas')
            self.assertEqual(captured[-1]['products'].total,5)
            self.client.get('/validades-proximas?loja_id=2&setor_id=1&busca=04')
            self.assertEqual([p.nome_produto for p in captured[-1]['products'].items],['Outra loja'])
        expired=Produto.query.filter_by(nome_produto='Vencido').one()
        expired.validade=agora_brasil().date()-timedelta(days=100)
        db.session.commit()
        response=self.client.get('/produtos/vencidos',follow_redirects=True)
        self.assertIn('Vencido há 100 dias',response.text)
        for path in ['/notifications','/notifications?status=all','/perfil','/historico','/produtos/novo?manual=1']:
            self.assertEqual(self.client.get(path).status_code,403,path)
        self.assertEqual(self.client.post('/notifications/read-all').status_code,403)

    def test_trade_alerts_cancelled_but_password_recovery_kept(self):
        self.preference(frequency='daily',hour=0,minute=0)
        queue_due_alerts()
        self.assertEqual(EmailDelivery.query.filter_by(kind='alert',status='pending').count(),1)
        self.use_role('gerente_trocas')
        sync_expiry_notifications()
        self.assertEqual(unread_query(self.user).count(),0)
        queue_due_alerts(agora_brasil()+timedelta(days=1))
        self.assertEqual(EmailDelivery.query.filter_by(kind='alert').count(),1)
        db.session.add(EmailDelivery(delivery_key='test-reset',user_id=self.user.id,kind='reset',
            recipient=self.user.username,subject='Redefina sua senha',body='test'))
        db.session.commit()
        self.app.config.update(MAIL_SERVER='test',MAIL_DEFAULT_SENDER='test@example.test')
        with patch('app.mail_service.send_message') as send:
            deliver_pending(utcnow()+timedelta(seconds=2))
            self.assertEqual(send.call_count,1)
        db.session.expire_all()
        self.assertEqual(EmailDelivery.query.filter_by(kind='alert').one().status,'cancelled')
        self.assertEqual(EmailDelivery.query.filter_by(kind='reset').one().status,'sent')

    def test_auxiliary_cannot_expand_store_scope(self):
        self.use_role('auxiliar_gestao')
        response=self.client.get('/validades-proximas?loja_id=2')
        self.assertNotIn('Outra loja',response.text)
