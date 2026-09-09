"""API autenticada de consulta ao catálogo compartilhado."""
from flask import Blueprint, jsonify, request
from flask_login import login_required
from sqlalchemy import or_, func
from .models import ProdutoCatalogo

catalog_api = Blueprint('catalog_api', __name__)


def serialize(item):
    return {'id': item.id, 'nome': item.nome_produto, 'plu': item.plu,
            'barcode': item.barcode_1 or item.barcode_2 or item.barcode_3,
            'barcodes': [b for b in (item.barcode_1, item.barcode_2, item.barcode_3) if b]}


def search_catalog(term):
    term = term.strip()
    if not term or len(term) > 100:
        return []
    columns = [ProdutoCatalogo.plu, ProdutoCatalogo.barcode_1,
               ProdutoCatalogo.barcode_2, ProdutoCatalogo.barcode_3]
    exact = ProdutoCatalogo.query.filter(or_(*(c == term for c in columns))).all()
    if exact:
        return [serialize(item) for item in exact[:20]]
    if len(term) < 2:
        return []
    matches = ProdutoCatalogo.query.filter(or_(
        func.lower(ProdutoCatalogo.nome_produto).contains(term.lower(), autoescape=True),
        *(c.contains(term, autoescape=True) for c in columns),
    )).order_by(ProdutoCatalogo.nome_produto, ProdutoCatalogo.id).limit(20).all()
    return [serialize(item) for item in matches]


@catalog_api.route('/api/buscar-catalogo')
@catalog_api.route('/api/catalogo')
@login_required
def search():
    return jsonify(search_catalog(request.args.get('term', '')))


@catalog_api.route('/api/buscar-produto/<code>')
@login_required
def barcode(code):
    if len(code) > 50:
        return jsonify(encontrado=False, mensagem='Código inválido.'), 400
    rows = ProdutoCatalogo.query.filter(or_(
        ProdutoCatalogo.plu == code, ProdutoCatalogo.barcode_1 == code,
        ProdutoCatalogo.barcode_2 == code, ProdutoCatalogo.barcode_3 == code,
    )).limit(2).all()
    if len(rows) > 1:
        return jsonify(encontrado=False, mensagem='Código associado a mais de um produto. Busque pelo nome.'), 409
    if not rows:
        return jsonify(encontrado=False, mensagem='Produto não encontrado no catálogo. Cadastre-o para continuar.'), 404
    return jsonify(**serialize(rows[0]), encontrado=True, fonte='Catálogo Veneza')
