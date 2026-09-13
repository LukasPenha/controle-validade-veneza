"""Registro de lote a partir de uma seleção assinada da API externa."""
from datetime import date
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from . import db
from .models import Produto, Setor, Loja
from .product_lookup import selected_product
from .notifications import sync_expiry_notifications, add_event
from .inventory import money

lots_bp = Blueprint('lots', __name__)
EDITORS = ('gerente_geral', 'gerente', 'encarregado_setor', 'auxiliar_gestao')


@lots_bp.route('/lotes/novo', methods=['GET', 'POST'])
@login_required
def create():
    if current_user.role not in EDITORS:
        abort(403)
    token = request.form.get('selection') if request.method == 'POST' else request.args.get('selection')
    manual = request.values.get('manual') == '1'
    product = None
    if not manual:
        try:
            product = selected_product(token)
        except ValueError as error:
            flash(str(error), 'warning')
            return redirect(url_for('routes.datas_curtas'))
    if request.method == 'POST':
        try:
            cost = money(request.form.get('custo_unitario'))
            if manual:
                name = request.form.get('nome_produto','').strip()
                code = request.form.get('barcode','').strip()
                brand = request.form.get('marca','').strip()
                import re
                if not 2 <= len(name) <= 200 or len(brand) > 150 or (code and not re.fullmatch('[0-9]{8,14}',code)):
                    raise ValueError()
                product = dict(nome=name,barcode=code,marca=brand,source='manual',source_url='')
            quantity = int(request.form.get('quantidade', ''))
            validity = date.fromisoformat(request.form.get('validade', ''))
            store = int(request.form.get('loja_id', '')) if current_user.role == 'gerente_geral' else current_user.loja_id
            sector = current_user.setor_id if current_user.role == 'encarregado_setor' else int(request.form.get('setor_id', ''))
            batch = request.form.get('lote', '').strip()
            reason = request.form.get('motivo_rebaixa', '').strip()
            plu = request.form.get('plu', '').strip()
            if not 1 <= quantity <= 2147483647 or not store or not sector:
                raise ValueError()
            if not db.session.get(Loja, store) or not db.session.get(Setor, sector):
                raise ValueError()
            if len(batch) > 80 or len(reason) > 255 or len(plu) > 50:
                raise ValueError()
            item = Produto(nome_produto=product['nome'], barcode=product['barcode'], marca=product['marca'],
                source=product['source'], source_url=product['source_url'], plu=plu, quantidade=quantity, custo_unitario=cost,
                validade=validity, loja_id=store, setor_id=sector, lote=batch, motivo_rebaixa=reason,
                criado_por_id=current_user.id)
            db.session.add(item)
            db.session.flush()
            add_event(item, f'created:{item.id}', 'created', 'info', f'{item.nome_produto}: lote registrado com {quantity} unidades.')
            db.session.commit()
            sync_expiry_notifications(user=current_user)
            flash('Lote registrado e notificações atualizadas.', 'success')
            return redirect(url_for('routes.datas_curtas'))
        except (ValueError, TypeError):
            db.session.rollback()
            flash('Confira quantidade positiva, validade, loja, setor e tamanho dos campos.', 'danger')
    return render_template('geral/registrar_lote.html', product=product, selection=token, manual=manual,
        stores=Loja.query.order_by(Loja.nome).all() if current_user.role == 'gerente_geral' else [],
        sectors=Setor.query.order_by(Setor.nome).all())
