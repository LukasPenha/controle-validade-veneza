"""Entrada da Vercel; migrações e tarefas periódicas são executadas fora da função."""
from sqlalchemy.pool import NullPool
from app import create_app

app = create_app({
    'SCHEDULER_ENABLED': False,
    'TRUSTED_PROXIES': 1,
    'LOGIN_IP_LIMIT_ENABLED': True,
    'SESSION_COOKIE_SECURE': True,
    'MAX_PHOTO_BYTES': 4 * 1024 * 1024,
    'MAX_CONTENT_LENGTH': 4 * 1024 * 1024 + 128 * 1024,
    # O Supabase transaction pooler gerencia as conexões entre invocações.
    'SQLALCHEMY_ENGINE_OPTIONS': {'poolclass': NullPool, 'pool_pre_ping': True},
})
