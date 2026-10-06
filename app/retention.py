"""Retenção de dados: encerra avisos informativos antigos e apaga registros técnicos vencidos.

O histórico de auditoria (AuditEvent) não é apagado: é o registro do que foi feito em cada produto.
"""
from datetime import timedelta
from flask import current_app
from sqlalchemy.exc import SQLAlchemyError
from . import db
from .models import Notificacao, NotificationRead, JobState, ExposureProof, Produto, utcnow
from .email_models import EmailDelivery, EmailToken

INFO_RESOLVE_DAYS = 30
NOTIFICATION_KEEP_DAYS = 180
EMAIL_KEEP_DAYS = 90
FINAL_EMAIL_STATUS = ('sent', 'skipped', 'cancelled', 'expired', 'failed', 'uncertain')


def purge_old_data(now=None):
    now = now or utcnow()
    counts = {}
    counts['avisos_encerrados'] = Notificacao.query.filter(
        Notificacao.severity == 'info', Notificacao.resolved_at.is_(None),
        Notificacao.timestamp < now - timedelta(days=INFO_RESOLVE_DAYS),
    ).update({'resolved_at': now}, synchronize_session=False)
    old = db.session.query(Notificacao.id).filter(
        Notificacao.resolved_at < now - timedelta(days=NOTIFICATION_KEEP_DAYS))
    NotificationRead.query.filter(NotificationRead.notificacao_id.in_(old)).delete(synchronize_session=False)
    counts['avisos_apagados'] = Notificacao.query.filter(
        Notificacao.resolved_at < now - timedelta(days=NOTIFICATION_KEEP_DAYS)).delete(synchronize_session=False)
    counts['emails_apagados'] = EmailDelivery.query.filter(
        EmailDelivery.status.in_(FINAL_EMAIL_STATUS),
        EmailDelivery.created_at < now - timedelta(days=EMAIL_KEEP_DAYS)).delete(synchronize_session=False)
    counts['tokens_apagados'] = EmailToken.query.filter(
        EmailToken.expires_at < now - timedelta(days=30)).delete(synchronize_session=False)
    db.session.commit()
    return counts


def purge_if_due(now=None):
    """Roda a limpeza no máximo uma vez por dia; o job de notificações chama a cada execução."""
    now = now or utcnow()
    try:
        state = db.session.get(JobState, 'purge')
        if state and state.last_success_at and state.last_success_at > now - timedelta(days=1):
            return None
        counts = purge_old_data(now)
        state = state or JobState(name='purge')
        state.last_success_at = now
        db.session.add(state)
        db.session.commit()
        return counts
    except SQLAlchemyError:
        # A limpeza nunca pode derrubar o job de alertas (ex.: banco ainda sem a migração nova).
        db.session.rollback()
        current_app.logger.exception('Falha na limpeza de dados antigos')
        return None


def old_photos(days):
    """Fotos de produtos já encerrados, enviadas há mais de `days` dias."""
    archived = db.session.query(Produto.id).filter(Produto.arquivado.is_(True))
    return ExposureProof.query.filter(ExposureProof.produto_id.in_(archived),
                                      ExposureProof.timestamp < utcnow() - timedelta(days=days))
