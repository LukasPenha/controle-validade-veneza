from .notifications import sync_expiry_notifications
from .retention import purge_if_due


def verificar_validades_diarias(app):
    """Varre todas as pendências, inclusive vencimentos ocorridos durante indisponibilidade."""
    with app.app_context():
        sync_expiry_notifications()
        purge_if_due()
