"""Prévia local com dados fictícios, sem conexão com banco ou e-mail de produção."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datetime import date, timedelta
from app import create_app, db
from app.models import Usuario, Loja, Setor, Produto, ProdutoCatalogo, agora_brasil

app = create_app({'SECRET_KEY': 'preview-only-secret-' * 3, 'SQLALCHEMY_DATABASE_URI': 'sqlite://',
                  'SCHEDULER_ENABLED': False, 'MAIL_SERVER': '', 'SESSION_COOKIE_SECURE': False})
with app.app_context():
    db.create_all()
    stores = [Loja(nome=name) for name in ['Veneza · Centro', 'Veneza · Jardins', 'Veneza · Norte']]
    sectors = [Setor(nome=name) for name in ['Mercearia', 'Laticínios', 'Bebidas']]
    db.session.add_all(stores + sectors)
    db.session.flush()
    for name, role in [('demo', 'gerente_geral'), ('setor', 'encarregado_setor'), ('gerente', 'gerente'), ('auxiliar', 'auxiliar_gestao'), ('trocas', 'gerente_trocas')]:
        user = Usuario(username=name, role=role, loja_id=stores[0].id, setor_id=sectors[0].id)
        user.set_password('Demo-veneza-2026')
        db.session.add(user)
    today = agora_brasil().date()
    names = ['Arroz branco tipo 1 · 5 kg', 'Café torrado tradicional · 500 g', 'Leite integral · 1 L',
             'Biscoito cream cracker · 400 g', 'Molho de tomate · 300 g', 'Suco de uva integral · 1 L']
    for i, name in enumerate(names):
        db.session.add(ProdutoCatalogo(nome_produto=name, plu=str(100+i), barcode_1=f'78900000000{i:02d}'))
    for month in range(1, 13):
        for i, name in enumerate(names):
            db.session.add(Produto(nome_produto=name, plu=str(100+i), quantidade=(month*17+i*13)%120+12,
                validade=date(today.year, month, 15), loja_id=stores[i%3].id, setor_id=sectors[i%3].id))
    for i, name in enumerate(names):
        db.session.add(Produto(nome_produto=name, plu=str(100+i), quantidade=36+i*12,
            validade=today+timedelta(days=i), loja_id=stores[0].id, setor_id=sectors[0].id))
    db.session.commit()

if __name__ == '__main__':
    from waitress import serve
    serve(app, host='127.0.0.1', port=8011)
