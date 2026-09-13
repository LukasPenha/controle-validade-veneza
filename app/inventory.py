"""Scoped lot operations and immutable movement values."""
from decimal import Decimal, InvalidOperation
import re
import secrets
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from . import db
from .models import Produto, Movimento, AuditEvent, agora_brasil
from .notifications import scope, sync_expiry_notifications, add_event

inventory_bp = Blueprint('inventory', __name__)
EDITORS = ('gerente_geral','gerente','encarregado_setor')


def money(raw, required=False):
    raw = (raw or '').strip().replace(',', '.')
    if not raw and not required:
        return None
    try:
        value = Decimal(raw)
        if not value.is_finite() or value < 0 or value > Decimal('9999999999.99') or value != value.quantize(Decimal('.01')):
            raise ValueError()
        return value.quantize(Decimal('.01'))
    except (InvalidOperation, ValueError):
        raise ValueError('Informe um valor positivo ou zero, com até duas casas decimais.') from None


def visible_lots():
    return scope(Produto.query, Produto, current_user)


@inventory_bp.get('/lotes')
@login_required
def index():
    state = request.args.get('situacao','abertos')
    query = visible_lots()
    if state == 'abertos':
        query = query.filter(Produto.quantidade > 0, Produto.arquivado.is_(False))
    elif state == 'encerrados':
        query = query.filter(db.or_(Produto.quantidade == 0, Produto.arquivado.is_(True)))
    elif state != 'todos':
        abort(400)
    term = request.args.get('busca','').strip()[:100]
    if term:
        query = query.filter(db.or_(Produto.nome_produto.ilike('%'+term+'%'), Produto.barcode == term))
    items = query.order_by(Produto.validade, Produto.id).paginate(page=request.args.get('page',1,type=int),per_page=20,error_out=False)
    return render_template('inventory/index.html',items=items,state=state,term=term)


@inventory_bp.route('/lotes/<int:item_id>', methods=['GET','POST'])
@login_required
def detail(item_id):
    query = visible_lots().filter_by(id=item_id)
    item = query.with_for_update().populate_existing().first_or_404() if request.method == 'POST' else query.first_or_404()
    if request.method == 'POST':
        if current_user.role not in EDITORS:
            abort(403)
        try:
            if item.arquivado:
                raise ValueError('Este lote está arquivado.')
            if request.form.get('action') == 'cost':
                item.custo_unitario = money(request.form.get('custo_unitario'),required=True)
                db.session.commit()
                flash('Custo atualizado. Baixas anteriores mantêm os valores registrados na ocasião.', 'success')
            else:
                kind = request.form.get('tipo')
                qty = int(request.form.get('quantidade',''))
                key = request.form.get('request_key','')
                reason = request.form.get('motivo','').strip()
                if kind not in ('venda','descarte','devolucao') or not re.fullmatch('[a-f0-9]{32}',key):
                    raise ValueError('Operação inválida. Atualize a página.')
                previous = Movimento.query.filter_by(request_key=key).first()
                if previous:
                    if previous.produto_id != item.id:
                        abort(409)
                    flash('Esta baixa já foi registrada.', 'info')
                    return redirect(url_for('inventory.detail', item_id=item.id))
                if not 1 <= qty <= item.quantidade:
                    raise ValueError('A quantidade deve ser maior que zero e não pode ultrapassar o saldo.')
                if not 3 <= len(reason) <= 255:
                    raise ValueError('Informe um motivo de 3 a 255 caracteres.')
                price = money(request.form.get('valor_unitario'), required=kind == 'venda') if kind != 'descarte' else None
                movement = Movimento(produto_id=item.id,request_key=key,tipo=kind,quantidade=qty,
                    custo_unitario=item.custo_unitario,valor_unitario=price,motivo=reason,actor=current_user.username)
                db.session.add(movement)
                item.quantidade -= qty
                add_event(item, f'movement:{key}', 'movement', 'info',
                    f'{item.nome_produto}: {qty} unidades em {kind}. Saldo: {item.quantidade}.')
                db.session.commit()
                sync_expiry_notifications(user=current_user)
                flash('Baixa registrada. Saldo e histórico atualizados.', 'success')
        except (ValueError, IntegrityError) as error:
            db.session.rollback()
            flash(str(error) if isinstance(error,ValueError) else 'Operação já processada ou em conflito. Confira o histórico.', 'warning')
        return redirect(url_for('inventory.detail',item_id=item.id))
    events = AuditEvent.query.filter_by(produto_id=item.id).order_by(AuditEvent.id.desc()).limit(100).all()
    movements = Movimento.query.filter_by(produto_id=item.id).order_by(Movimento.id.desc()).limit(100).all()
    return render_template('inventory/detail.html',item=item,events=events,movements=movements,
        editable=current_user.role in EDITORS,request_key=secrets.token_hex(16))


@inventory_bp.get('/historico')
@login_required
def history():
    query = scope(AuditEvent.query, AuditEvent, current_user)
    events = query.order_by(AuditEvent.id.desc()).paginate(page=request.args.get('page',1,type=int),per_page=30,error_out=False)
    return render_template('inventory/history.html',events=events)


def financial_data(year, store=0, sector=0):
    from datetime import datetime
    from .models import BRASIL
    query = Movimento.query.join(Produto,Produto.id == Movimento.produto_id).filter(
        Movimento.timestamp >= datetime(year,1,1,tzinfo=BRASIL),
        Movimento.timestamp < datetime(year+1,1,1,tzinfo=BRASIL))
    if store:
        query = query.filter(Produto.loja_id == store)
    if sector:
        query = query.filter(Produto.setor_id == sector)
    values = {}
    for kind in ('venda','descarte','devolucao'):
        row = query.filter(Movimento.tipo == kind).with_entities(
            func.coalesce(func.sum(Movimento.quantidade),0),
            func.coalesce(func.sum(Movimento.quantidade * Movimento.custo_unitario),0),
            func.coalesce(func.sum(Movimento.quantidade * Movimento.valor_unitario),0),
            func.count().filter(Movimento.custo_unitario.is_(None)),
            func.count().filter(Movimento.valor_unitario.is_(None))).one()
        values[kind] = dict(units=row[0],cost=row[1],value=row[2],missing_cost=row[3],missing_value=row[4])
    return values
