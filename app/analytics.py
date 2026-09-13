"""Consultas agregadas do painel, sem carregar todo o estoque em memória."""
from datetime import date, timedelta
from flask import abort, request
from sqlalchemy import func, extract
from .models import Produto, Loja, Setor, agora_brasil

MONTHS = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez']


def dashboard_data():
    today = agora_brasil().date()
    year = request.args.get('year', today.year, type=int)
    month = request.args.get('month', 0, type=int)
    horizon = request.args.get('horizon', 30, type=int)
    store = request.args.get('store', 0, type=int)
    sector = request.args.get('sector', 0, type=int)
    mode = request.args.get('mode', 'all')
    if not 2000 <= year <= 2100 or not 0 <= month <= 12 or horizon not in (7, 15, 30, 60, 90) or mode not in ('all', 'expired', 'soon'):
        abort(400)
    query = Produto.query.filter(Produto.quantidade > 0, Produto.arquivado.is_(False))
    if store:
        query = query.filter(Produto.loja_id == store)
    if sector:
        query = query.filter(Produto.setor_id == sector)
    yearly = query.filter(Produto.validade >= date(year, 1, 1), Produto.validade < date(year + 1, 1, 1))
    monthly = yearly.with_entities(extract('month', Produto.validade).label('month'),
        func.sum(Produto.quantidade), func.count(Produto.id)).group_by(extract('month', Produto.validade)).all()
    values = {int(m): (int(q or 0), n) for m, q, n in monthly}
    bars = [{'month': i, 'label': label, 'units': values.get(i, (0, 0))[0],
             'records': values.get(i, (0, 0))[1]} for i, label in enumerate(MONTHS, 1)]
    max_units = max([b['units'] for b in bars] + [1])
    for bar in bars:
        bar['height'] = round(bar['units'] / max_units * 100, 1)
    expired = query.filter(Produto.validade < today)
    soon = query.filter(Produto.validade >= today, Produto.validade <= today + timedelta(days=horizon))
    def totals(q):
        units, records = q.with_entities(func.coalesce(func.sum(Produto.quantidade), 0), func.count(Produto.id)).one()
        return {'units': units, 'records': records}
    def ranking(q):
        return q.with_entities(Produto.barcode.label('code'), func.min(Produto.nome_produto).label('name'),
            func.sum(Produto.quantidade).label('units'), func.count(Produto.id).label('records')).group_by(
                Produto.barcode, Produto.nome_produto).order_by(func.sum(Produto.quantidade).desc(), Produto.barcode).limit(5).all()
    detail_query = yearly
    if month:
        detail_query = detail_query.filter(extract('month', Produto.validade) == month)
    if mode == 'expired':
        detail_query = detail_query.filter(Produto.validade < today)
    elif mode == 'soon':
        detail_query = detail_query.filter(Produto.validade >= today, Produto.validade <= today + timedelta(days=horizon))
    products = detail_query.order_by(Produto.validade, Produto.id).paginate(
        page=request.args.get('page', 1, type=int), per_page=15, error_out=False)
    from .inventory import financial_data
    return dict(finances=financial_data(year,store,sector), today=today, year=year, month=month, horizon=horizon, store=store, sector=sector,
        mode=mode, bars=bars, yearly=totals(yearly), expired=totals(expired), soon=totals(soon),
        urgent=totals(query.filter(Produto.validade >= today, Produto.validade <= today + timedelta(days=7))),
        expired_ranking=ranking(expired), soon_ranking=ranking(soon), products=products,
        stores=Loja.query.order_by(Loja.nome).all(), sectors=Setor.query.order_by(Setor.nome).all())
