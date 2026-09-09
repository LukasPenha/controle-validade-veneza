from .notifications import sync_expiry_notifications


def verificar_validades_diarias(app):
    """Varre todas as pendências, inclusive vencimentos ocorridos durante indisponibilidade."""
    with app.app_context():
        sync_expiry_notifications()
