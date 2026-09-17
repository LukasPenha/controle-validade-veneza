"""Preferências pessoais e entrega de e-mails com escopo por usuário."""
import hashlib
import re
import secrets
from datetime import timedelta, time
from urllib.parse import urlsplit

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from . import db
from .models import Usuario, Produto, agora_brasil, utcnow
from .email_models import EmailPreference, EmailToken, EmailDelivery
from .mail_service import queue_due_alerts, deliver_pending, process_email_jobs, scoped_products

profile_bp = Blueprint('profile', __name__)




def valid_email(value):
    value = (value or '').strip().lower()
    if len(value) > 254 or not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+', value):
        raise ValueError('Informe um endereço de e-mail válido.')
    return value


def fingerprint(user):
    return hashlib.sha256(user.password_hash.encode()).hexdigest()




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
    now = utcnow()
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
    if not token or token.used or token.purpose != purpose or token.expires_at <= utcnow():
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
                    EmailDelivery.created_at > utcnow() - timedelta(minutes=5)).first()
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
    history = EmailDelivery.query.filter_by(user_id=current_user.id).order_by(EmailDelivery.created_at.desc()).limit(10).all()
    return render_template('profile.html', pref=pref, deliveries=history)


@profile_bp.route('/confirmar-email/<token>', methods=['GET', 'POST'])
def verify(token):
    record = find_token(token, 'verify')
    pref = db.session.get(EmailPreference, record.user_id) if record else None
    owner = db.session.get(Usuario, record.user_id) if record else None
    valid = bool(pref and owner and owner.role != 'gerente_trocas' and pref.address == record.address)
    if valid and request.method == 'POST':
        if claim_token(record):
            pref.verified = True
            db.session.commit()
            flash('E-mail confirmado. Seus alertas seguirão a programação do perfil.', 'success')
            return redirect(url_for('auth.login'))
        db.session.rollback()
        valid = False
    return render_template('auth_action.html', mode='verify', valid=valid)
