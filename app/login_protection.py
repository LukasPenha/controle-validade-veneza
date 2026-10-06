"""Shared, atomic limits; never trust forwarded headers supplied by a visitor."""
import hashlib
import hmac
from datetime import timedelta
from flask import current_app, request
from sqlalchemy.exc import IntegrityError
from . import db
from .models import LoginLimit, utcnow


def allow_attempt(username):
    now = utcnow()
    LoginLimit.query.filter(LoginLimit.expires_at <= now).delete(synchronize_session=False)
    # With the IP limit on, the attacker's own IP is blocked first (20) and the
    # account limit (50) is high enough that a single attacker cannot lock out
    # the real owner. Without it, the account limit stays strict (10).
    account = 'account:' + username.strip().casefold()[:254]
    if current_app.config.get('LOGIN_IP_LIMIT_ENABLED'):
        identities = [('ip:' + (request.remote_addr or 'unknown'), 20), (account, 50)]
    else:
        identities = [(account, 10)]
    for identity, maximum in identities:
        key = hmac.new(current_app.secret_key.encode(), identity.encode(), hashlib.sha256).hexdigest()
        if not db.session.get(LoginLimit, key):
            try:
                with db.session.begin_nested():
                    db.session.add(LoginLimit(key=key, attempts=0, expires_at=now+timedelta(minutes=15)))
                    db.session.flush()
            except IntegrityError:
                pass
        claimed = LoginLimit.query.filter(LoginLimit.key == key, LoginLimit.attempts < maximum).update(
            {'attempts': LoginLimit.attempts+1})
        if not claimed:
            db.session.commit()
            return False
    db.session.commit()
    return True
