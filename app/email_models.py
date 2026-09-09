"""Preferências e fila durável de e-mail, com invariantes no banco."""
from . import db
from .models import UTCDateTime, utcnow


class EmailPreference(db.Model):
    __tablename__ = 'email_preference'
    __table_args__ = (
        db.CheckConstraint("frequency IN ('daily','weekly')", name='ck_email_frequency'),
        db.CheckConstraint('weekday BETWEEN 0 AND 6', name='ck_email_weekday'),
        db.CheckConstraint('hour BETWEEN 0 AND 23 AND minute BETWEEN 0 AND 59', name='ck_email_time'),
        db.CheckConstraint('days_min >= 0 AND days_max >= days_min AND days_max <= 365', name='ck_email_window'),
        db.Index('ix_email_schedule', 'enabled', 'verified', 'frequency', 'weekday', 'hour'),
    )
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
    __table_args__ = (
        db.CheckConstraint("purpose IN ('reset','verify')", name='ck_token_purpose'),
        db.Index('ix_token_user_purpose', 'user_id', 'purpose', 'used'),
    )
    digest = db.Column(db.String(64), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('usuario.id', ondelete='CASCADE'), nullable=False)
    purpose = db.Column(db.String(10), nullable=False)
    address = db.Column(db.String(254), nullable=False)
    password_stamp = db.Column(db.String(64), nullable=False)
    expires_at = db.Column(UTCDateTime(), nullable=False, index=True)
    used = db.Column(db.Boolean, nullable=False, default=False)


class EmailDelivery(db.Model):
    __tablename__ = 'email_delivery'
    __table_args__ = (
        db.CheckConstraint("status IN ('pending','sending','sent','skipped','cancelled','expired','failed','uncertain')", name='ck_delivery_status'),
        db.CheckConstraint('attempts >= 0', name='ck_delivery_attempts'),
        db.Index('ix_delivery_pending', 'status', 'next_attempt_at'),
        db.Index('ix_delivery_user_created', 'user_id', 'created_at'),
    )
    id = db.Column(db.Integer, primary_key=True)
    delivery_key = db.Column(db.String(160), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('usuario.id', ondelete='CASCADE'), nullable=False)
    kind = db.Column(db.String(10), nullable=False)
    recipient = db.Column(db.String(254), nullable=False)
    subject = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(UTCDateTime(), nullable=False, default=utcnow)
    scheduled_for = db.Column(UTCDateTime(), nullable=False, default=utcnow)
    status = db.Column(db.String(10), nullable=False, default='pending')
    attempts = db.Column(db.Integer, nullable=False, default=0)
    next_attempt_at = db.Column(UTCDateTime(), nullable=False, default=utcnow)
    started_at = db.Column(UTCDateTime())
    sent_at = db.Column(UTCDateTime())
    last_error = db.Column(db.String(160))
