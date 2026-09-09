"""Add email preferences, single-use tokens and delivery queue to existing installation.

Revision ID: 20260909_email
Revises: None (repository has no prior versioned migrations)
"""
from alembic import op
import sqlalchemy as sa

revision = '20260909_email'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('email_preference',
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('usuario.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('address', sa.String(254), nullable=False),
        sa.Column('verified', sa.Boolean(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('frequency', sa.String(10), nullable=False),
        sa.Column('weekday', sa.Integer(), nullable=False),
        sa.Column('hour', sa.Integer(), nullable=False),
        sa.Column('minute', sa.Integer(), nullable=False),
        sa.Column('days_min', sa.Integer(), nullable=False),
        sa.Column('days_max', sa.Integer(), nullable=False),
    )
    op.create_table('email_token',
        sa.Column('digest', sa.String(64), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('usuario.id', ondelete='CASCADE'), nullable=False),
        sa.Column('purpose', sa.String(10), nullable=False),
        sa.Column('address', sa.String(254), nullable=False),
        sa.Column('password_stamp', sa.String(64), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('used', sa.Boolean(), nullable=False),
    )
    op.create_table('email_delivery',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('delivery_key', sa.String(120), nullable=False, unique=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('usuario.id', ondelete='CASCADE'), nullable=False),
        sa.Column('kind', sa.String(10), nullable=False),
        sa.Column('recipient', sa.String(254), nullable=False),
        sa.Column('subject', sa.String(200), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('status', sa.String(10), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
    )


def downgrade():
    op.drop_table('email_delivery')
    op.drop_table('email_token')
    op.drop_table('email_preference')
