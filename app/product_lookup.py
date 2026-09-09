"""Read-only Open Food Facts adapter, with shared quotas and short-lived cache."""
from datetime import timedelta
import hashlib
import re
import requests
from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required
from itsdangerous import URLSafeTimedSerializer, BadData
from sqlalchemy.exc import IntegrityError
from . import db
from .models import ApiBudget, ExternalLookupCache, utcnow

lookup_bp = Blueprint('lookup', __name__)
BASE = 'https://world.openfoodfacts.org'
FIELDS = 'code,product_name,product_name_pt,brands,quantity'


class LookupUnavailable(Exception):
    def __init__(self, message, status=503):
        super().__init__(message)
        self.status = status


def normalize_product(raw):
    if not isinstance(raw, dict):
        return None
    code = str(raw.get('code') or '')
    name = raw.get('product_name_pt') or raw.get('product_name')
    if not re.fullmatch(r'\d{8,14}', code) or not isinstance(name, str) or not name.strip():
        return None
    return {'barcode': code, 'nome': name.strip()[:200],
            'marca': str(raw.get('brands') or '')[:150],
            'embalagem': str(raw.get('quantity') or '')[:80],
            'source': 'openfoodfacts', 'source_url': BASE + '/product/' + code}


def reserve_request(kind):
    now = utcnow()
    delay = 8 if kind == 'search' else 5
    if not db.session.get(ApiBudget, kind):
        try:
            with db.session.begin_nested():
                db.session.add(ApiBudget(name=kind, next_allowed_at=now))
                db.session.flush()
        except IntegrityError:
            pass
    claimed = ApiBudget.query.filter(ApiBudget.name == kind, ApiBudget.next_allowed_at <= now).update(
        {'next_allowed_at': now + timedelta(seconds=delay)})
    db.session.commit()
    if not claimed:
        raise LookupUnavailable('Aguarde alguns segundos antes de outra consulta. A API gratuita limita as buscas.', 429)


def lookup_products(term):
    term = term.strip()
    if not 2 <= len(term) <= 100:
        raise LookupUnavailable('Informe de 2 a 100 caracteres para pesquisar.', 400)
    numeric = term.isdecimal()
    if numeric and not re.fullmatch(r'\d{8,14}', term):
        raise LookupUnavailable('Informe um código de barras com 8 a 14 dígitos. O PLU interno não é consultado pela API.', 400)
    key = hashlib.sha256(term.casefold().encode()).hexdigest()
    cached = db.session.get(ExternalLookupCache, key)
    now = utcnow()
    if cached and cached.expires_at > now:
        return cached.payload
    reserve_request('barcode' if numeric else 'search')
    path = f'/api/v3/product/{term}.json' if numeric else '/cgi/search.pl'
    params = {'fields': FIELDS}
    if not numeric:
        params.update(search_terms=term, search_simple=1, action='process', json=1,
                      page_size=12, page=1, lc='pt')
    try:
        response = requests.get(BASE + path, params=params,
            headers={'User-Agent': current_app.config['PRODUCT_API_USER_AGENT'], 'Accept': 'application/json'},
            timeout=(3, 10), allow_redirects=False)
        if response.status_code == 429:
            raise LookupUnavailable('O serviço de produtos atingiu o limite. Tente novamente em um minuto.', 429)
        if response.status_code == 404 and numeric:
            data = {}
        else:
            response.raise_for_status()
            if response.status_code != 200:
                raise LookupUnavailable('O serviço de produtos está indisponível no momento.')
            data = response.json()
        if not isinstance(data, dict):
            raise LookupUnavailable('O serviço retornou uma resposta inválida. Tente novamente.')
        raw = [data.get('product')] if numeric else data.get('products', [])
        if not isinstance(raw, list):
            raise LookupUnavailable('O serviço retornou uma resposta inválida. Tente novamente.')
        products = [p for p in (normalize_product(item) for item in raw[:12]) if p]
        products = list({p['barcode']: p for p in products}.values())
    except (requests.RequestException, ValueError):
        raise LookupUnavailable('Não foi possível consultar os produtos. Verifique a conexão e tente novamente.') from None
    expires = now + timedelta(minutes=60 if products else 5)
    if cached:
        cached.payload, cached.expires_at = products, expires
    else:
        db.session.add(ExternalLookupCache(key=key, payload=products, expires_at=expires))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
    return products


def serializer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'], salt='external-product-selection-v2')


def selection_token(product):
    return serializer().dumps({'user': current_user.id, 'product': product})


def selected_product(token):
    if not isinstance(token, str) or not token:
        raise ValueError('Pesquise e selecione o produto antes de registrar o lote.')
    try:
        data = serializer().loads(token, max_age=1800)
        if data['user'] != current_user.id or data['product']['source'] != 'openfoodfacts':
            raise ValueError()
        return data['product']
    except (BadData, KeyError, TypeError, ValueError):
        raise ValueError('A seleção expirou ou é inválida. Pesquise e selecione o produto novamente.') from None


@lookup_bp.get('/api/produtos')
@login_required
def search():
    try:
        products = lookup_products(request.args.get('term', ''))
        return jsonify(products=[dict(p, selection=selection_token(p)) for p in products], source='Open Food Facts')
    except LookupUnavailable as error:
        response = jsonify(error=str(error), products=[])
        response.status_code = error.status
        if error.status == 429:
            response.headers['Retry-After'] = '60'
        return response
