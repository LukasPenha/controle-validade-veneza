"""Audit trail written in the same transaction as each lot mutation."""
from sqlalchemy import event, inspect
from sqlalchemy.orm import Session
from flask import has_request_context
from flask_login import current_user
from .models import Produto, AuditEvent

FIELDS = ('nome_produto','barcode','source','marca','lote','quantidade','custo_unitario',
          'validade','status','loja_id','setor_id','motivo_rebaixa','arquivado')


def value(raw):
    return None if raw is None else str(raw)


@event.listens_for(Session, 'before_flush')
def capture_changes(session, flush_context, instances):
    pending = []
    for item in list(session.new) + list(session.dirty) + list(session.deleted):
        if not isinstance(item, Produto):
            continue
        state = inspect(item)
        created = item in session.new
        if not created and any(state.attrs[field].history.has_changes() for field in ('validade','quantidade','status','loja_id','setor_id')):
            item.exposure_revision = (item.exposure_revision or 1) + 1
        changes = {}
        for field in FIELDS:
            history = state.attrs[field].history
            if created or history.has_changes():
                changes[field] = {'antes': value(history.deleted[0]) if history.deleted else None,
                                  'depois': value(getattr(item, field))}
        if not changes and item not in session.deleted:
            continue
        actor = current_user.username if has_request_context() and current_user.is_authenticated else 'Sistema'
        action = 'exclusao' if item in session.deleted else 'criacao' if created else 'alteracao'
        pending.append((item, actor, action, changes))
    session.info['lot_audit'] = pending


@event.listens_for(Session, 'after_flush_postexec')
def persist_changes(session, flush_context):
    for item, actor, action, changes in session.info.pop('lot_audit', []):
        if action == 'criacao':
            for field in FIELDS:
                changes[field]['depois'] = value(getattr(item, field))
        session.add(AuditEvent(produto_id=item.id, loja_id=item.loja_id, setor_id=item.setor_id,
            actor=actor, action=action, changes=changes))
