import re
import unittest
from flask import g
from unittest.mock import patch

from app import create_app, db
from app.models import Loja, Setor, Usuario, Produto, Notificacao, agora_brasil
from app.tasks import verificar_validades_diarias


class SecurityTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({
            'TESTING': True, 'SECRET_KEY': 'test-secret-' * 4,
            'SQLALCHEMY_DATABASE_URI': 'sqlite://',
        })
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        loja = Loja(nome='A')
        outra = Loja(nome='B')
        setor = Setor(nome='Setor')
        db.session.add_all([loja, outra, setor])
        db.session.flush()
        user = Usuario(username='gerente', role='gerente', loja_id=loja.id)
        user.set_password('senha-teste')
        db.session.add(user)
        produto = Produto(nome_produto='Produto', plu='1', quantidade=1,
                          barcode='3017620422003', source_url='https://world.openfoodfacts.org/product/3017620422003',
                          validade=agora_brasil().date(), loja_id=outra.id, setor_id=setor.id)
        db.session.add(produto)
        db.session.commit()
        self.product_id = produto.id
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def token(self):
        html = self.client.get('/login').get_data(as_text=True)
        return re.search(r'name="csrf_token" value="([^"]+)"', html)[1]

    def login(self):
        response = self.client.post('/login', data={
            'username': 'gerente', 'password': 'senha-teste', 'csrf_token': self.token(),
        })
        g.pop('csrf_token', None)
        return response

    def test_csrf_rejects_missing_and_forged_tokens(self):
        for token in ('', 'invalid'):
            response = self.client.post('/login', data={'csrf_token': token})
            self.assertEqual(response.status_code, 400)

    def test_https_login_preserves_same_origin_referrer_and_csrf(self):
        base = 'https://localhost'
        response = self.client.get('/login', base_url=base)
        html = response.get_data(as_text=True)
        self.assertIn('name="referrer" content="same-origin"', html)
        self.assertNotIn('content="no-referrer"', html)
        token = re.search(r'name="csrf_token" value="([^"]+)"', html)[1]
        data = {'username': 'gerente', 'password': 'senha-teste', 'csrf_token': token}
        for headers in ({}, {'Referer': 'https://outside.example/login'}):
            self.assertEqual(self.client.post('/login', base_url=base,
                                             data=data, headers=headers).status_code, 400)
        self.assertEqual(self.client.post('/login', base_url=base,
            data={**data, 'csrf_token': 'invalid'},
            headers={'Referer': base + '/login'}).status_code, 400)
        response = self.client.post('/login', base_url=base, data=data,
                                    headers={'Referer': base + '/login'})
        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as session:
            self.assertIn('_user_id', session)

    def test_login_and_logout_require_valid_post(self):
        self.assertEqual(self.login().status_code, 302)
        self.assertEqual(self.client.get('/logout').status_code, 405)
        self.assertEqual(self.client.post('/logout').status_code, 400)
        html = self.client.get('/gerente/para-rebaixa').get_data(as_text=True)
        token = re.search(r'name="csrf_token" value="([^"]+)"', html)[1]
        self.assertEqual(self.client.post('/logout', data={'csrf_token': token}).status_code, 302)
        self.assertEqual(self.client.get('/gerente/para-rebaixa').status_code, 302)

    def test_manager_cannot_delete_other_store_product(self):
        self.login()
        html = self.client.get('/gerente/para-rebaixa').get_data(as_text=True)
        token = re.search(r'name="csrf_token" value="([^"]+)"', html)[1]
        self.client.post(f'/produtos/{self.product_id}/excluir', data={'csrf_token': token})
        self.assertIsNotNone(db.session.get(Produto, self.product_id))

    def test_task_uses_existing_application(self):
        with patch('app.create_app', side_effect=AssertionError('Must reuse app')):
            verificar_validades_diarias(self.app)
        self.assertEqual(Notificacao.query.count(), 1)

    def test_security_headers(self):
        response = self.client.get('/login')
        self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
        self.assertIn('SameSite=Lax', response.headers['Set-Cookie'])

    def test_insecure_secret_rejected(self):
        with self.assertRaises(RuntimeError):
            create_app({'TESTING': True, 'SECRET_KEY': 'short', 'SQLALCHEMY_DATABASE_URI': 'sqlite://'})


if __name__ == '__main__':
    unittest.main()


class SessionTimeoutTests(unittest.TestCase):
    def setUp(self):
        import test_features as fixtures
        fixtures.FeatureTests.setUp(self)

    def tearDown(self):
        import test_features as fixtures
        fixtures.FeatureTests.tearDown(self)

    def login(self):
        return self.client.post('/login', data={'username': self.user.username, 'password': 'Original-12345'})

    def shift(self, key, seconds):
        with self.client.session_transaction() as sess:
            sess[key] -= seconds

    def test_idle_session_expires(self):
        self.login()
        self.assertEqual(self.client.get('/perfil').status_code, 200)
        self.shift('last_seen', self.app.config['SESSION_IDLE_MINUTES'] * 60 + 1)
        response = self.client.get('/perfil')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.location)
        self.assertEqual(self.client.get('/perfil').status_code, 302)

    def test_active_session_has_absolute_limit(self):
        self.login()
        with self.client.session_transaction() as sess:
            self.assertTrue(sess.permanent)
        self.shift('login_at', int(self.app.config['PERMANENT_SESSION_LIFETIME'].total_seconds()) + 1)
        self.assertEqual(self.client.get('/api/produtos?term=arroz').status_code, 401)

    def test_unknown_user_still_runs_bcrypt(self):
        from unittest.mock import patch
        from app import bcrypt
        with patch.object(bcrypt, 'check_password_hash', wraps=bcrypt.check_password_hash) as check:
            self.client.post('/login', data={'username': 'ninguem@example.test', 'password': 'Qualquer-12345'})
        self.assertEqual(check.call_count, 1)
