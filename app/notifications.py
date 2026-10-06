"""Central de alertas: escopo, eventos únicos e leitura explícita."""
from datetime import timedelta
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError
from . import db
from .models import Notificacao, NotificationRead, Produto, JobState, ExternalLookupCache, utcnow, agora_brasil

notifications_bp = Blueprint('notifications', __name__)


def scope(query, model, user):
    if user.role in ('gerente_geral', 'gerente_trocas'):
        return query
    if user.role not in ('gerente', 'auxiliar_gestao', 'encarregado_setor') or not user.loja_id:
        return query.filter(db.false())
    query = query.filter(model.loja_id == user.loja_id)
    if user.role == 'encarregado_setor':
        return query.filter(model.setor_id == user.setor_id) if user.setor_id else query.filter(db.false())
    return query


def unread_query(user):
    if user.role == 'gerente_trocas':
        return Notificacao.query.filter(db.false())
    read_ids = db.session.query(NotificationRead.notificacao_id).filter_by(usuario_id=user.id)
    return scope(Notificacao.query, Notificacao, user).filter(
        Notificacao.resolved_at.is_(None), ~Notificacao.id.in_(read_ids))


def expiry_event(product, today):
    if product.quantidade == 0 or product.arquivado:
        return None
    days = (product.validade - today).days
    if days > 7:
        return None
    kind = 'expired' if days < 0 else ('due_today' if days == 0 else 'approaching')
    severity = 'critical' if days <= 0 else 'warning'
    text = 'está vencido' if days < 0 else ('vence hoje' if days == 0 else f'vence em {days} dias')
    return kind, severity, f'{product.nome_produto}: {text}. {product.quantidade} unidades · validade {product.validade:%d/%m/%Y}.'


def add_event(product, key, kind, severity, message, checked=False):
    if not checked and Notificacao.query.filter_by(event_key=key).first():
        return
    try:
        with db.session.begin_nested():
            db.session.add(Notificacao(event_key=key, produto_id=product.id, loja_id=product.loja_id,
                setor_id=product.setor_id, kind=kind, severity=severity, mensagem=message))
            db.session.flush()
    except IntegrityError:
        # A concurrent worker has already generated this exact event.
        pass


EXPIRY_KINDS = ('expired', 'due_today', 'approaching')


def _sync(active, products, now):
    """Resolve alertas vencidos e cria/reativa os atuais com uma consulta por lote de 500 chaves."""
    today = now.date()
    for item in active:
        event = expiry_event(item.produto, today)
        expected = f'expiry:{item.produto_id}:{item.produto.validade}:{event[0]}' if event else None
        if item.event_key != expected:
            item.resolved_at = now
        elif event:
            item.mensagem = event[2]
    wanted = {}
    for product in products:
        event = expiry_event(product, today)
        if event:
            wanted[f'expiry:{product.id}:{product.validade}:{event[0]}'] = (product, event)
    keys = list(wanted)
    existing = {}
    for start in range(0, len(keys), 500):
        for row in Notificacao.query.filter(Notificacao.event_key.in_(keys[start:start + 500])):
            existing[row.event_key] = row
    for key, (product, (kind, severity, message)) in wanted.items():
        if key in existing:
            existing[key].resolved_at = None
            existing[key].mensagem = message
        else:
            add_event(product, key, kind, severity, message, checked=True)


def sync_product_notifications(product, now=None):
    """Atualiza só o produto alterado; a varredura completa fica com o job agendado."""
    active = Notificacao.query.filter(Notificacao.resolved_at.is_(None), Notificacao.kind.in_(EXPIRY_KINDS),
                                      Notificacao.produto_id == product.id).all()
    _sync(active, [product], now or agora_brasil())
    db.session.commit()


def sync_expiry_notifications(now=None, user=None):
    now = now or agora_brasil()
    today = now.date()
    active = Notificacao.query.filter(Notificacao.resolved_at.is_(None), Notificacao.kind.in_(EXPIRY_KINDS))
    if user:
        active = scope(active, Notificacao, user)
    query = Produto.query.filter(Produto.validade <= today + timedelta(days=7), Produto.quantidade > 0, Produto.arquivado.is_(False))
    if user:
        query = scope(query, Produto, user)
    _sync(active.all(), query.all(), now)
    if not user:
        ExternalLookupCache.query.filter(ExternalLookupCache.expires_at <= utcnow()).delete()
        job = db.session.get(JobState, 'expiry')
        if not job:
            job = JobState(name='expiry')
            db.session.add(job)
        job.last_success_at = now
    db.session.commit()


@notifications_bp.route('/notifications')
@login_required
def center():
    status = request.args.get('status', 'unread')
    query = scope(Notificacao.query, Notificacao, current_user)
    if status == 'unread':
        query = unread_query(current_user)
    elif status == 'active':
        query = query.filter(Notificacao.resolved_at.is_(None))
    elif status != 'all':
        abort(400)
    severity = request.args.get('severity', '')
    if severity in ('warning', 'critical', 'info'):
        query = query.filter_by(severity=severity)
    items = query.order_by(Notificacao.timestamp.desc(), Notificacao.id.desc()).paginate(
        page=request.args.get('page', 1, type=int), per_page=20, error_out=False)
    read_ids = {row.notificacao_id for row in NotificationRead.query.filter(
        NotificationRead.usuario_id == current_user.id,
        NotificationRead.notificacao_id.in_([item.id for item in items.items])).all()}
    return render_template('geral/notifications.html', items=items, read_ids=read_ids,
        status=status, severity=severity, job=db.session.get(JobState, 'expiry'))


@notifications_bp.post('/notifications/<int:notification_id>/read')
@login_required
def mark_read(notification_id):
    item = scope(Notificacao.query, Notificacao, current_user).filter_by(id=notification_id).first_or_404()
    key = {'usuario_id': current_user.id, 'notificacao_id': item.id}
    if not db.session.get(NotificationRead, key):
        try:
            db.session.add(NotificationRead(**key))
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
    return redirect(url_for('notifications.center'))


@notifications_bp.post('/notifications/read-all')
@login_required
def mark_all_read():
    for item in unread_query(current_user).all():
        try:
            with db.session.begin_nested():
                db.session.add(NotificationRead(usuario_id=current_user.id, notificacao_id=item.id))
                db.session.flush()
        except IntegrityError:
            pass
    db.session.commit()
    flash('Notificações atuais marcadas como lidas.', 'success')
    return redirect(url_for('notifications.center'))


@notifications_bp.post('/notifications/refresh')
@login_required
def refresh():
    sync_expiry_notifications(user=current_user)
    flash('Validades verificadas para sua área de acesso.', 'success')
    return redirect(url_for('notifications.center'))
