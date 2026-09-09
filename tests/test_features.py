import unittest
from datetime import date, datetime, timedelta
from unittest.mock import patch
from tempfile import TemporaryDirectory
from pathlib import Path
from flask import g

from app import create_app, db
from app.analytics import dashboard_data
from app.models import Usuario, Loja, Setor, Produto, ProdutoCatalogo, agora_brasil
from app.preferences import (EmailPreference, EmailDelivery, issue_token,
                             find_token, queue_due_alerts, deliver_pending)


class FeatureTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({'TESTING': True, 'SECRET_KEY': 'feature-tests-'*4,
            'SQLALCHEMY_DATABASE_URI': 'sqlite://', 'WTF_CSRF_ENABLED': False,
            'PUBLIC_BASE_URL': 'https://example.test', 'MAIL_SERVER': '',
            'SESSION_COOKIE_SECURE': False})
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        stores = [Loja(nome='A'), Loja(nome='B')]
        sectors = [Setor(nome='Mercearia'), Setor(nome='Bebidas')]
        db.session.add_all(stores + sectors)
        db.session.flush()
        self.user = Usuario(username='user@example.test', role='encarregado_setor', loja_id=1, setor_id=1)
        self.user.set_password('Original-12345')
        db.session.add(self.user)
        self.today = agora_brasil().date()
        for name, store, sector, days, quantity, plu in [
            ('Arroz',1,1,0,10,'01'),('Arroz',1,1,7,20,'01'),('Fora da faixa',1,1,8,30,'02'),
            ('Outro setor',1,2,2,40,'03'),('Outra loja',2,1,2,50,'04'),('Vencido',1,1,-1,60,'05')]:
            db.session.add(Produto(nome_produto=name, plu=plu, loja_id=store, setor_id=sector,
                quantidade=quantity, validade=self.today+timedelta(days=days)))
        db.session.add(ProdutoCatalogo(nome_produto='Arroz', plu='01', barcode_1='0789000000012', barcode_2='12345678'))
        db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def login(self):
        return self.client.post('/login', data={'username':self.user.username,'password':'Original-12345'})

    def preference(self, **kwargs):
        values = dict(user_id=self.user.id, address='alert@example.test', verified=True,
                      enabled=True, frequency='weekly', weekday=2, hour=9, minute=0, days_min=0, days_max=7)
        values.update(kwargs)
        pref = EmailPreference(**values)
        db.session.add(pref)
        db.session.commit()
        return pref

    def test_weekly_schedule_scope_bounds_and_no_duplicate(self):
        self.preference()
        # Use a Wednesday while keeping date bounds aligned with the test products.
        now = agora_brasil().replace(hour=9,minute=0)
        pref = db.session.get(EmailPreference,self.user.id)
        pref.weekday = now.weekday()
        db.session.commit()
        queue_due_alerts(now.replace(hour=8,minute=59))
        self.assertEqual(EmailDelivery.query.count(),0)
        queue_due_alerts(now)
        queue_due_alerts(now.replace(hour=10))
        self.assertEqual(EmailDelivery.query.count(),1)
        body = EmailDelivery.query.one().body
        self.assertEqual(body.count('Arroz'),2)
        for excluded in ['Outra loja','Outro setor','Vencido','Fora da faixa']:
            self.assertNotIn(excluded,body)
        queue_due_alerts(now+timedelta(days=1))
        self.assertEqual(EmailDelivery.query.count(),1)

    def test_daily_schedule_and_empty_summary(self):
        self.preference(frequency='daily',days_min=300,days_max=301)
        now = agora_brasil().replace(hour=10)
        queue_due_alerts(now)
        queue_due_alerts(now+timedelta(days=1))
        self.assertEqual(EmailDelivery.query.count(),2)
        self.assertTrue(all(d.status == 'skipped' for d in EmailDelivery.query.all()))

    def test_unverified_or_disabled_does_not_queue(self):
        self.preference(verified=False)
        queue_due_alerts(agora_brasil().replace(hour=23))
        self.assertEqual(EmailDelivery.query.count(),0)

    def test_invalid_profile_does_not_save(self):
        self.login()
        response = self.client.post('/perfil', data={'address':'alert@example.test','current_password':'Original-12345',
            'frequency':'daily','send_time':'09:00','days_min':'10','days_max':'2'})
        self.assertEqual(response.status_code,200)
        self.assertIsNone(db.session.get(EmailPreference,self.user.id))

    def test_profile_email_confirmation_and_change(self):
        self.login()
        data = dict(address='alert@example.test',current_password='Original-12345',frequency='weekly',
                    weekday='2',send_time='09:00',days_min='0',days_max='7',enabled='on')
        self.assertEqual(self.client.post('/perfil',data=data).status_code,302)
        pref = db.session.get(EmailPreference,self.user.id)
        self.assertFalse(pref.verified)
        raw = EmailDelivery.query.one().body.split('/confirmar-email/')[1].split()[0]
        self.assertEqual(self.client.get('/confirmar-email/'+raw).status_code,200)
        self.assertFalse(pref.verified)  # Opening links in email scanners must not consume them.
        self.client.post('/confirmar-email/'+raw)
        self.assertTrue(pref.verified)
        data['address'] = 'other@example.test'
        self.client.post('/perfil',data=data)
        self.assertFalse(pref.verified)

    def test_reset_single_use_expiry_and_old_sessions(self):
        self.login()
        raw = issue_token(self.user,'reset',self.user.username)
        db.session.commit()
        self.assertIsNotNone(find_token(raw,'reset'))
        other = self.app.test_client()
        self.assertEqual(other.post('/redefinir-senha/'+raw,data={
            'password':'Nova-senha-12345','confirmation':'Nova-senha-12345'}).status_code,302)
        self.assertTrue(self.user.check_password('Nova-senha-12345'))
        self.assertIsNone(find_token(raw,'reset'))
        # This test keeps an app context across requests; simulate a fresh request's user cache.
        g.pop('_login_user', None)
        self.assertEqual(self.client.get('/perfil').status_code,302)
        expired = issue_token(self.user,'reset',self.user.username)
        db.session.flush()
        record = find_token(expired,'reset')
        record.expires_at = datetime.utcnow()-timedelta(seconds=1)
        db.session.commit()
        self.assertIsNone(find_token(expired,'reset'))

    def test_reset_does_not_reveal_account_and_throttles(self):
        for email in [self.user.username,self.user.username,'nobody@example.test']:
            response = self.client.post('/esqueci-senha',data={'email':email},follow_redirects=True)
            self.assertIn('Se houver uma conta',response.get_data(as_text=True))
        self.assertEqual(EmailDelivery.query.count(),1)

    def test_dashboard_units_records_filters_and_months(self):
        self.user.role='gerente_geral'
        db.session.commit()
        self.login()
        with self.app.test_request_context(f'/gerente-geral/dashboard?year={self.today.year}&store=1&sector=1&horizon=7'):
            data=dashboard_data()
            self.assertEqual(len(data['bars']),12)
            self.assertEqual(data['soon']['units'],30)
            self.assertEqual(data['soon']['records'],2)
            self.assertEqual(data['expired']['units'],60)
            self.assertEqual(data['soon_ranking'][0].units,30)
        self.assertEqual(self.client.get('/gerente-geral/dashboard').status_code,200)
        self.assertEqual(self.client.get('/gerente-geral/dashboard?month=13').status_code,400)

    def test_dashboard_is_general_manager_only(self):
        self.login()
        self.assertEqual(self.client.get('/gerente-geral/dashboard').status_code,302)

    def test_catalog_api_preserves_zeros_and_matches_all_barcodes(self):
        self.assertEqual(self.client.get('/api/catalogo?term=Arroz').status_code,401)
        self.login()
        for term in ['arroz','01','0789000000012','12345678']:
            data=self.client.get('/api/catalogo',query_string={'term':term}).get_json()
            self.assertEqual(data[0]['nome'],'Arroz')
            self.assertEqual(data[0]['barcode'],'0789000000012')
        self.assertEqual(self.client.get('/api/catalogo?term=%25').get_json(),[])
        self.assertEqual(self.client.get('/api/buscar-produto/missing').status_code,404)

    def test_registration_uses_catalog_and_assigned_sector(self):
        self.login()
        self.client.post('/cadastrar-rebaixa',data={'catalogo_id':'1','nome_produto':'Tampered',
            'plu':'Fake','quantidade':'5','validade':str(self.today),'setor_id':'2'})
        product=Produto.query.order_by(Produto.id.desc()).first()
        self.assertEqual((product.nome_produto,product.plu,product.setor_id),('Arroz','01',1))
        before=Produto.query.count()
        self.client.post('/cadastrar-rebaixa',data={'catalogo_id':'1','quantidade':'-1','validade':str(self.today)})
        self.assertEqual(Produto.query.count(),before)

    def test_delivery_rechecks_scope_after_role_change(self):
        self.preference(frequency='daily')
        queue_due_alerts(agora_brasil().replace(hour=10))
        self.user.setor_id=2
        db.session.commit()
        self.app.config.update(MAIL_SERVER='smtp.example.test',MAIL_DEFAULT_SENDER='sender@example.test')
        with patch('app.preferences.smtplib.SMTP') as smtp:
            deliver_pending()
            message=smtp.return_value.__enter__.return_value.send_message.call_args[0][0]
            self.assertIn('Outro setor',message.get_content())
            self.assertNotIn('Arroz',message.get_content())
        self.assertEqual(EmailDelivery.query.one().status,'sent')


class MigrationTests(unittest.TestCase):
    def test_migration_preserves_existing_user(self):
        from flask_migrate import upgrade
        with TemporaryDirectory() as folder:
            app=create_app({'TESTING':True,'SECRET_KEY':'migration-key-'*4,
                'SQLALCHEMY_DATABASE_URI':'sqlite:///'+str(Path(folder)/'legacy.db')})
            with app.app_context():
                original=[table for table in db.metadata.sorted_tables if not table.name.startswith('email_')]
                db.metadata.create_all(db.engine,tables=original)
                user=Usuario(username='existing',role='gerente_geral')
                user.set_password('Original-12345')
                db.session.add(user)
                db.session.commit()
                upgrade(directory='migrations')
                self.assertEqual(Usuario.query.count(),1)
                self.assertEqual(EmailPreference.query.count(),0)
                db.session.remove()
                db.engine.dispose()


if __name__ == '__main__':
    unittest.main()
