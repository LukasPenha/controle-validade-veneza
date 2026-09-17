"""Fila de envio com prioridade, confirmação de escopo e recuperação de falhas."""
from datetime import timedelta, datetime, time
from email.message import EmailMessage
import smtplib
import ssl
from flask import current_app
from sqlalchemy.exc import IntegrityError
from . import db
from .models import Usuario, Produto, BRASIL, JobState, utcnow, agora_brasil
from .email_models import EmailPreference, EmailDelivery
from .notifications import scope


def scoped_products(user):
    return scope(Produto.query, Produto, user).filter(Produto.quantidade > 0, Produto.arquivado.is_(False))


def alert_content(user, pref, today):
    products = scoped_products(user).filter(
        Produto.validade >= today + timedelta(days=pref.days_min),
        Produto.validade <= today + timedelta(days=pref.days_max),
    ).order_by(Produto.validade, Produto.id).all()
    units = sum(p.quantidade for p in products)
    subject = f'Veneza | {units} unidades em {len(products)} produtos próximos do vencimento'
    body = (f'Olá, {user.nome_display}.\nResumo de {today:%d/%m/%Y}: de {pref.days_min} a {pref.days_max} dias.\n\n'
            + '\n'.join(f'{p.nome_produto} | Código {p.barcode} | '
                        f'{p.quantidade} un. | {p.validade:%d/%m/%Y} | {p.loja.nome} / {p.setor.nome}' for p in products)
            + '\n\nAjuste a frequência ou desative os e-mails em Meu perfil e alertas.')
    return products, subject, body


def queue_due_alerts(now=None):
    now = now or agora_brasil()
    for pref in EmailPreference.query.filter_by(enabled=True, verified=True).all():
        if pref.frequency == 'weekly' and now.weekday() != pref.weekday:
            continue
        due = datetime.combine(now.date(), time(pref.hour, pref.minute), tzinfo=BRASIL)
        if now < due:
            continue
        key = f'alert:{pref.user_id}:{now.date()}'
        if EmailDelivery.query.filter_by(delivery_key=key).first():
            continue
        user = db.session.get(Usuario, pref.user_id)
        if not user or user.role == 'gerente_trocas':
            continue
        products, subject, body = alert_content(user, pref, now.date())
        try:
            with db.session.begin_nested():
                db.session.add(EmailDelivery(delivery_key=key, user_id=user.id, kind='alert', recipient=pref.address,
                    subject=subject, body=body if products else '', scheduled_for=due,
                    status='pending' if products else 'skipped'))
                db.session.flush()
        except IntegrityError:
            pass
    db.session.commit()


def send_message(message):
    config = current_app.config
    if config['MAIL_TRANSPORT'] == 'gmail_api':
        from .gmail_transport import send_gmail
        return send_gmail(message)
    if config['MAIL_TRANSPORT'] != 'smtp':
        raise ValueError('Transporte de e-mail inválido.')
    if not config['MAIL_USE_SSL'] and not config['MAIL_USE_TLS']:
        raise ValueError('SMTP exige TLS ou SSL.')
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


def deliver_pending(now=None):
    now = now or utcnow()
    trade_users = db.session.query(Usuario.id).filter_by(role='gerente_trocas')
    EmailDelivery.query.filter(EmailDelivery.user_id.in_(trade_users),
        EmailDelivery.kind.in_(['alert','verify']), EmailDelivery.status == 'pending').update(
            {'status':'cancelled', 'body':''}, synchronize_session=False)
    # Do not blindly resend an interrupted SMTP transaction: it may already have been accepted.
    EmailDelivery.query.filter(EmailDelivery.status == 'sending',
        EmailDelivery.started_at < now - timedelta(minutes=10)).update({
            'status': 'uncertain', 'body': '', 'last_error': 'Processamento interrompido; entrega não confirmada.'})
    EmailDelivery.query.filter(EmailDelivery.status == 'pending', EmailDelivery.kind != 'alert',
        EmailDelivery.created_at < now - timedelta(minutes=30)).update({'status': 'expired', 'body': ''})
    db.session.commit()
    config = current_app.config
    configured = all(config.get(key) for key in ('GMAIL_CLIENT_ID','GMAIL_CLIENT_SECRET','GMAIL_REFRESH_TOKEN')) if config['MAIL_TRANSPORT'] == 'gmail_api' else bool(config.get('MAIL_SERVER'))
    if not configured or not config.get('MAIL_DEFAULT_SENDER'):
        return
    rows = EmailDelivery.query.filter(EmailDelivery.status == 'pending', EmailDelivery.next_attempt_at <= now).order_by(
        (EmailDelivery.kind == 'alert').asc(), EmailDelivery.created_at).limit(30).all()
    for item in rows:
        if item.kind == 'alert':
            pref = db.session.get(EmailPreference, item.user_id)
            user = db.session.get(Usuario, item.user_id)
            local_now = now.astimezone(BRASIL)
            if item.scheduled_for.astimezone(BRASIL).date() != local_now.date():
                item.status, item.body = 'expired', ''
                db.session.commit()
                continue
            if not user or user.role == 'gerente_trocas' or not pref or not pref.enabled or not pref.verified or pref.address != item.recipient:
                item.status, item.body = 'cancelled', ''
                db.session.commit()
                continue
            if (pref.frequency == 'weekly' and pref.weekday != local_now.weekday()) or (local_now.hour, local_now.minute) < (pref.hour, pref.minute):
                continue
            products, item.subject, item.body = alert_content(user, pref, local_now.date())
            if not products:
                item.status, item.body = 'skipped', ''
                db.session.commit()
                continue
        claimed = EmailDelivery.query.filter_by(id=item.id, status='pending').update(
            {'status': 'sending', 'started_at': now, 'attempts': EmailDelivery.attempts + 1})
        db.session.commit()
        if not claimed:
            continue
        try:
            message = EmailMessage()
            message['From'] = current_app.config['MAIL_DEFAULT_SENDER']
            message['To'] = item.recipient
            message['Subject'] = item.subject
            message['Message-ID'] = f'<veneza-{item.id}-{item.created_at.timestamp():.0f}@notifications.local>'
            message.set_content(item.body)
            send_message(message)
            item.status, item.sent_at, item.last_error, item.body = 'sent', now, None, ''
        except (TimeoutError, smtplib.SMTPServerDisconnected):
            item.status, item.last_error, item.body = 'uncertain', 'Conexão interrompida; entrega não confirmada.', ''
        except (OSError, smtplib.SMTPException, ValueError):
            item.last_error = 'Serviço de e-mail indisponível ou configuração recusada.'
            item.status = 'failed' if item.attempts >= 3 else 'pending'
            item.next_attempt_at = now + timedelta(minutes=2 ** item.attempts)
            if item.status == 'failed':
                item.body = ''
        db.session.commit()


def process_email_jobs(app):
    with app.app_context():
        queue_due_alerts()
        deliver_pending()
        state = db.session.get(JobState, 'email')
        if not state:
            state = JobState(name='email')
            db.session.add(state)
        state.last_success_at = utcnow()
        db.session.commit()
