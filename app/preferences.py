"""Preferências pessoais e entrega de e-mails com escopo por usuário."""
import hashlib
import re
import secrets
import smtplib
import ssl
from datetime import datetime, timedelta, time
from email.message import EmailMessage
from urllib.parse import urlsplit

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from . import db
from .models import Usuario, Produto, agora_brasil

profile_bp = Blueprint('profile', __name__)


class EmailPreference(db.Model):
    __tablename__ = 'email_preference'
    user_id = db.Column(db.Integer, db.ForeignKey('usuario.id', ondelete='CASCADE'), primary_key=True)
    address = db.Column(db.String(254), nullable=False)
    verified = db.Column(db.Boolean, nullable=False, default=False)
    enabled = db.Column(db.Boolean, nullable=False, default=False)
    frequency = db.Column(db.String(10), nullable=False, default='daily')
    weekday = db.Column(db.Integer, nullable=False, default=2)
    hour = db.Column(db.Integer, nullable=False, default=9)
    minute = db.Column(db.Integer, nullable=False, default=0)
    days_min = db.Column(db.Integer, nullable=False, default=0)
    days_max = db.Column(db.Integer, nullable=False, default=7)


class EmailToken(db.Model):
    __tablename__ = 'email_token'
    digest = db.Column(db.String(64), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('usuario.id', ondelete='CASCADE'), nullable=False)
    purpose = db.Column(db.String(10), nullable=False)
    address = db.Column(db.String(254), nullable=False)
    password_stamp = db.Column(db.String(64), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, nullable=False, default=False)


class EmailDelivery(db.Model):
    __tablename__ = 'email_delivery'
    id = db.Column(db.Integer, primary_key=True)
    delivery_key = db.Column(db.String(120), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('usuario.id', ondelete='CASCADE'), nullable=False)
    kind = db.Column(db.String(10), nullable=False)
    recipient = db.Column(db.String(254), nullable=False)
    subject = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    status = db.Column(db.String(10), nullable=False, default='pending')
    attempts = db.Column(db.Integer, nullable=False, default=0)


def valid_email(value):
    value = (value or '').strip().lower()
    if len(value) > 254 or not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+', value):
        raise ValueError('Informe um endereço de e-mail válido.')
    return value


def fingerprint(user):
    return hashlib.sha256(user.password_hash.encode()).hexdigest()


def scoped_products(user):
    query = Produto.query
    if user.role in ('gerente_geral', 'gerente_trocas'):
        return query
    if user.role not in ('gerente', 'encarregado_setor', 'auxiliar_gestao') or not user.loja_id:
        return query.filter(db.false())
    query = query.filter(Produto.loja_id == user.loja_id)
    if user.role == 'encarregado_setor':
        if not user.setor_id:
            return query.filter(db.false())
        query = query.filter(Produto.setor_id == user.setor_id)
    return query


def public_link(endpoint, **values):
    base = current_app.config.get('PUBLIC_BASE_URL', '').rstrip('/')
    parsed = urlsplit(base)
    if parsed.scheme != 'https' or not parsed.netloc or parsed.username or parsed.query or parsed.fragment:
        raise ValueError('Configure PUBLIC_BASE_URL com o endereço HTTPS do sistema.')
    return base + current_app.url_map.bind(parsed.netloc).build(endpoint, values)


def issue_token(user, purpose, address):
    raw = secrets.token_urlsafe(32)
    endpoint = 'profile.verify' if purpose == 'verify' else 'auth.reset_password'
    link = public_link(endpoint, token=raw)
    now = datetime.utcnow()
    EmailToken.query.filter_by(user_id=user.id, purpose=purpose, used=False).update({'used': True})
    db.session.add(EmailToken(
        digest=hashlib.sha256(raw.encode()).hexdigest(), user_id=user.id,
        purpose=purpose, address=address, password_stamp=fingerprint(user),
        expires_at=now + timedelta(minutes=30),
    ))
    subject = 'Confirme seu e-mail de alertas' if purpose == 'verify' else 'Redefina sua senha'
    db.session.add(EmailDelivery(
        delivery_key=secrets.token_hex(24), user_id=user.id, kind=purpose,
        recipient=address, subject=f'Veneza | {subject}',
        body=f'{subject} no Controle de Validade Veneza.\n\n{link}\n\n'
             'Este link expira em 30 minutos e só pode ser usado uma vez. '
             'Se você não solicitou, ignore esta mensagem.',
    ))
    return raw


def find_token(raw, purpose):
    if len(raw) > 200:
        return None
    token = db.session.get(EmailToken, hashlib.sha256(raw.encode()).hexdigest())
    if not token or token.used or token.purpose != purpose or token.expires_at <= datetime.utcnow():
        return None
    user = db.session.get(Usuario, token.user_id)
    if not user or token.password_stamp != fingerprint(user):
        return None
    if purpose == 'reset' and user.username.lower() != token.address:
        return None
    return token


def claim_token(token):
    return EmailToken.query.filter_by(digest=token.digest, used=False).update({'used': True}) == 1


@profile_bp.route('/perfil', methods=['GET', 'POST'])
@login_required
def settings():
    pref = db.session.get(EmailPreference, current_user.id)
    if request.method == 'POST':
        try:
            address = valid_email(request.form.get('address'))
            frequency = request.form.get('frequency')
            weekday = int(request.form.get('weekday', '2'))
            send_time = time.fromisoformat(request.form.get('send_time', '09:00'))
            low = int(request.form.get('days_min', '0'))
            high = int(request.form.get('days_max', '7'))
            if frequency not in ('daily', 'weekly') or not 0 <= weekday <= 6 or not 0 <= low <= high <= 365:
                raise ValueError('Confira a frequência e a faixa de 0 a 365 dias.')
            changed = not pref or pref.address != address
            if changed and not current_user.check_password(request.form.get('current_password', '')):
                raise ValueError('Informe sua senha atual para cadastrar ou alterar o e-mail.')
            if not pref:
                pref = EmailPreference(user_id=current_user.id, address=address)
                db.session.add(pref)
            pref.address = address
            pref.enabled = request.form.get('enabled') == 'on'
            pref.frequency, pref.weekday = frequency, weekday
            pref.hour, pref.minute = send_time.hour, send_time.minute
            pref.days_min, pref.days_max = low, high
            if changed:
                pref.verified = False
                issue_token(current_user, 'verify', address)
            elif not pref.verified and request.form.get('resend'):
                recent = EmailDelivery.query.filter_by(user_id=current_user.id, kind='verify').filter(
                    EmailDelivery.created_at > datetime.utcnow() - timedelta(minutes=5)).first()
                if recent:
                    raise ValueError('Aguarde cinco minutos antes de solicitar outra confirmação.')
                issue_token(current_user, 'verify', address)
            db.session.commit()
            flash('Preferências salvas. Confirme o e-mail recebido para habilitar os alertas.' if not pref.verified
                  else 'Preferências de alertas atualizadas.', 'success')
            return redirect(url_for('profile.settings'))
        except (ValueError, TypeError) as error:
            db.session.rollback()
            flash(str(error) if isinstance(error, ValueError) else 'Preencha todos os campos corretamente.', 'danger')
    return render_template('profile.html', pref=pref)


@profile_bp.route('/confirmar-email/<token>', methods=['GET', 'POST'])
def verify(token):
    record = find_token(token, 'verify')
    pref = db.session.get(EmailPreference, record.user_id) if record else None
    valid = bool(pref and pref.address == record.address)
    if valid and request.method == 'POST':
        if claim_token(record):
            pref.verified = True
            db.session.commit()
            flash('E-mail confirmado. Seus alertas seguirão a programação do perfil.', 'success')
            return redirect(url_for('auth.login'))
        db.session.rollback()
        valid = False
    return render_template('auth_action.html', mode='verify', valid=valid)


def queue_due_alerts(now=None):
    now = now or agora_brasil()
    for pref in EmailPreference.query.filter_by(enabled=True, verified=True).all():
        if pref.frequency == 'weekly' and now.weekday() != pref.weekday:
            continue
        if (now.hour, now.minute) < (pref.hour, pref.minute):
            continue
        user = db.session.get(Usuario, pref.user_id)
        if not user:
            continue
        key = f'alert:{user.id}:{now.date().isoformat()}'
        if EmailDelivery.query.filter_by(delivery_key=key).first():
            continue
        products = scoped_products(user).filter(
            Produto.validade >= now.date() + timedelta(days=pref.days_min),
            Produto.validade <= now.date() + timedelta(days=pref.days_max),
        ).order_by(Produto.validade, Produto.nome_produto).all()
        lines = [f'{p.nome_produto} | PLU {p.plu} | {p.quantidade} un. | '
                 f'{p.validade:%d/%m/%Y} | {p.loja.nome} / {p.setor.nome}' for p in products]
        db.session.add(EmailDelivery(
            delivery_key=key, user_id=user.id, kind='alert', recipient=pref.address,
            subject=f'Veneza | {len(products)} registros próximos do vencimento',
            body=f'Olá, {user.nome_display}.\nValidades entre {pref.days_min} e {pref.days_max} dias.\n\n'
                 + '\n'.join(lines) + '\n\nAjuste os próximos envios em Meu perfil.',
            status='pending' if products else 'skipped',
        ))
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()


def deliver_pending():
    config = current_app.config
    if not config.get('MAIL_SERVER') or not config.get('MAIL_DEFAULT_SENDER'):
        return
    for delivery in EmailDelivery.query.filter_by(status='pending').order_by(EmailDelivery.id).limit(50).all():
        if delivery.kind == 'alert':
            pref = db.session.get(EmailPreference, delivery.user_id)
            # A profile change cancels messages already waiting for delivery.
            if not pref or not pref.enabled or not pref.verified or pref.address != delivery.recipient:
                delivery.status = 'cancelled'
                delivery.body = ''
                db.session.commit()
                continue
            user = db.session.get(Usuario, delivery.user_id)
            today = agora_brasil().date()
            products = scoped_products(user).filter(
                Produto.validade >= today + timedelta(days=pref.days_min),
                Produto.validade <= today + timedelta(days=pref.days_max),
            ).order_by(Produto.validade, Produto.nome_produto).all() if user else []
            if not products:
                delivery.status = 'skipped'
                delivery.body = ''
                db.session.commit()
                continue
            # Recheck role/store/sector at delivery, including after an administrator edits the user.
            delivery.subject = f'Veneza | {len(products)} registros próximos do vencimento'
            delivery.body = f'Olá, {user.nome_display}.\nValidades de {pref.days_min} a {pref.days_max} dias.\n\n' + '\n'.join(
                f'{p.nome_produto} | PLU {p.plu} | {p.quantidade} un. | {p.validade:%d/%m/%Y} | {p.loja.nome} / {p.setor.nome}'
                for p in products) + '\n\nAjuste os próximos envios em Meu perfil.'
        if delivery.created_at < datetime.utcnow() - timedelta(minutes=30 if delivery.kind != 'alert' else 1440):
            delivery.status = 'expired'
            delivery.body = ''
            db.session.commit()
            continue
        claimed = EmailDelivery.query.filter_by(id=delivery.id, status='pending').update({'status': 'sending'})
        db.session.commit()
        if not claimed:
            continue
        try:
            message = EmailMessage()
            message['From'] = config['MAIL_DEFAULT_SENDER']
            message['To'] = delivery.recipient
            message['Subject'] = delivery.subject
            message.set_content(delivery.body)
            smtp_class = smtplib.SMTP_SSL if config['MAIL_USE_SSL'] else smtplib.SMTP
            options = {'timeout': 20}
            if config['MAIL_USE_SSL']:
                options['context'] = ssl.create_default_context()
            with smtp_class(config['MAIL_SERVER'], config['MAIL_PORT'], **options) as smtp:
                if config['MAIL_USE_TLS'] and not config['MAIL_USE_SSL']:
                    smtp.starttls(context=ssl.create_default_context())
                if config.get('MAIL_USERNAME'):
                    smtp.login(config['MAIL_USERNAME'], config['MAIL_PASSWORD'])
                smtp.send_message(message)
            delivery.status = 'sent'
            delivery.body = ''
        except (OSError, smtplib.SMTPException):
            current_app.logger.error('Falha SMTP na entrega %s; confira a configuração do serviço.', delivery.id)
            delivery.attempts += 1
            delivery.status = 'failed' if delivery.attempts >= 3 else 'pending'
        db.session.commit()


def process_email_jobs(app):
    with app.app_context():
        queue_due_alerts()
        deliver_pending()
