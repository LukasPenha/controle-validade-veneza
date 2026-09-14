import unittest
from datetime import timedelta
from flask import template_rendered
import test_features as fixtures
from app import db
from app.models import Produto


class UpcomingTests(unittest.TestCase):
    setUp = fixtures.FeatureTests.setUp
    tearDown = fixtures.FeatureTests.tearDown
    login = fixtures.FeatureTests.login

    def context_for(self, path):
        captured = []
        def capture(sender, template, context, **extra):
            captured.append(context)
        with template_rendered.connected_to(capture, self.app):
            response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        return response.text, captured[-1]

    def test_boundaries_order_scope_and_expired(self):
        self.login()
        for days in [31,30,16,15,11,10]:
            db.session.add(Produto(nome_produto=f'Prazo {days}',barcode='',plu=str(days),source='manual',source_url='',
                quantidade=1,loja_id=1,setor_id=1,validade=self.today+timedelta(days=days)))
        db.session.commit()
        html, context = self.context_for('/validades-proximas')
        dates = [(p.validade-self.today).days for p in context['products'].items]
        self.assertEqual(dates, [0,7,8,10,11,15,16,30])
        self.assertEqual(context['expired_count'], 1)
        for days, tone in [(10,'red'),(11,'yellow'),(15,'yellow'),(16,'green'),(30,'green')]:
            self.assertIn(f'expiry-{tone}">{days} dias restantes', html)
        _, context = self.context_for('/validades-proximas?dias=10')
        self.assertEqual(context['products'].total, 4)
        _, context = self.context_for('/validades-proximas?situacao=vencidos')
        self.assertEqual([p.nome_produto for p in context['products'].items], ['Vencido'])

    def test_filters_archive_and_access(self):
        self.assertEqual(self.client.get('/validades-proximas').status_code,302)
        self.login()
        _, context = self.context_for('/validades-proximas?dias=0')
        self.assertEqual(context['products'].total,1)
        item = context['products'].items[0]
        item.arquivado = True
        db.session.commit()
        _, context = self.context_for('/validades-proximas?dias=0')
        self.assertEqual(context['products'].total,0)
        for query in ['dias=-1','dias=366','situacao=invalid']:
            self.assertEqual(self.client.get('/validades-proximas?'+query).status_code,400)
        _, context = self.context_for('/validades-proximas?busca=02')
        self.assertEqual([p.nome_produto for p in context['products'].items],['Fora da faixa'])
