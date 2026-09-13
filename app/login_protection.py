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
    # Account limit follows the account across IP changes. Proxy IP limit is opt-in.
    identities = [('account:' + username.strip().casefold()[:254], 10)]
    if current_app.config.get('LOGIN_IP_LIMIT_ENABLED'):
        identities.append(('ip:' + (request.remote_addr or 'unknown'), 60))
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
