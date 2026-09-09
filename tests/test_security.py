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
                          validade=agora_brasil().date(), loja_id=outra.id, setor_id=setor.id)
        db.session.add(produto)
        db.session.commit()
        self.product_id = produto.id
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
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
