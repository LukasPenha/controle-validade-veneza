"""Esquema da instalação nova: lotes operacionais, sem catálogo de produtos."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import hashlib
import hmac

from flask_login import UserMixin
from sqlalchemy.types import TypeDecorator, DateTime
from . import db, bcrypt, login_manager

BRASIL = ZoneInfo('America/Sao_Paulo')
ROLES = ('gerente_geral', 'gerente_trocas', 'gerente', 'encarregado_setor', 'auxiliar_gestao')


def utcnow():
    return datetime.now(timezone.utc)


def agora_brasil():
    return utcnow().astimezone(BRASIL)


class UTCDateTime(TypeDecorator):
    """TIMESTAMPTZ no PostgreSQL; normaliza também o banco SQLite dos testes."""
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


@login_manager.user_loader
def load_user(user_id):
    try:
        identity, _ = user_id.split(':', 1)
        user = db.session.get(Usuario, int(identity))
        return user if user and hmac.compare_digest(user.get_id(), user_id) else None
    except (AttributeError, TypeError, ValueError):
        return None


class Loja(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), unique=True, nullable=False)
    cnpj = db.Column(db.String(18), unique=True)
    endereco = db.Column(db.String(255))
    cidade = db.Column(db.String(100))
    estado = db.Column(db.String(2))
    usuarios = db.relationship('Usuario', backref='loja', lazy=True)
    produtos = db.relationship('Produto', backref='loja', lazy=True)


class Setor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(50), unique=True, nullable=False)
    produtos = db.relationship('Produto', backref='setor', lazy=True)
    usuarios = db.relationship('Usuario', backref='setor', lazy=True)


class Usuario(db.Model, UserMixin):
    __table_args__ = (
        db.CheckConstraint("role IN ('gerente_geral','gerente_trocas','gerente','encarregado_setor','auxiliar_gestao')", name='ck_usuario_role'),
        db.CheckConstraint("role IN ('gerente_geral','gerente_trocas') OR loja_id IS NOT NULL", name='ck_usuario_loja'),
        db.CheckConstraint("role != 'encarregado_setor' OR setor_id IS NOT NULL", name='ck_usuario_setor'),
        db.Index('uq_usuario_username_lower', db.func.lower(db.column('username')), unique=True),
    )
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(254), nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(50), nullable=False, default='auxiliar_gestao')
    loja_id = db.Column(db.Integer, db.ForeignKey('loja.id', ondelete='RESTRICT'), index=True)
    setor_id = db.Column(db.Integer, db.ForeignKey('setor.id', ondelete='RESTRICT'), index=True)
    produtos_criados = db.relationship('Produto', backref='criado_por', lazy=True, passive_deletes=True)

    def get_id(self):
        stamp = hashlib.sha256(self.password_hash.encode()).hexdigest()
        return f'{self.id}:{stamp}'

    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        return bool(password) and bcrypt.check_password_hash(self.password_hash, password)

    @property
    def nome_display(self):
        return self.username.split('@')[0].capitalize() if '@' in self.username else self.username


class Produto(db.Model):
    __table_args__ = (
        db.CheckConstraint('quantidade >= 0', name='ck_produto_quantidade'),
        db.CheckConstraint('custo_unitario IS NULL OR custo_unitario >= 0', name='ck_produto_custo'),
        db.CheckConstraint("status IN ('Para Rebaixa','Em Rebaixa')", name='ck_produto_status'),
        db.CheckConstraint("source IN ('openfoodfacts','manual')", name='ck_produto_source'),
        db.Index('ix_produto_loja_setor_validade', 'loja_id', 'setor_id', 'validade'),
        db.Index('ix_produto_status_validade', 'status', 'validade'),
    )
    id = db.Column(db.Integer, primary_key=True)
    nome_produto = db.Column(db.String(200), nullable=False)
    # The scanned GTIN is the identity; PLU remains optional internal information.
    barcode = db.Column(db.String(14), nullable=False, index=True)
    plu = db.Column(db.String(50), nullable=False, default='')
    source = db.Column(db.String(30), nullable=False, default='openfoodfacts')
    source_url = db.Column(db.String(255), nullable=False)
    marca = db.Column(db.String(150), nullable=False, default='')
    lote = db.Column(db.String(80), nullable=False, default='')
    quantidade = db.Column(db.Integer, nullable=False)
    custo_unitario = db.Column(db.Numeric(12, 2))
    arquivado = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    exposure_revision = db.Column(db.Integer, nullable=False, default=1, server_default='1')
    validade = db.Column(db.Date, nullable=False, index=True)
    status = db.Column(db.String(50), nullable=False, default='Para Rebaixa')
    data_cadastro = db.Column(UTCDateTime(), nullable=False, default=utcnow)
    motivo_rebaixa = db.Column(db.String(255))
    loja_id = db.Column(db.Integer, db.ForeignKey('loja.id', ondelete='RESTRICT'), nullable=False)
    setor_id = db.Column(db.Integer, db.ForeignKey('setor.id', ondelete='RESTRICT'), nullable=False)
    criado_por_id = db.Column(db.Integer, db.ForeignKey('usuario.id', ondelete='SET NULL'), index=True)


class Notificacao(db.Model):
    __table_args__ = (
        db.Index('ix_notificacao_scope', 'loja_id', 'setor_id', 'resolved_at', 'timestamp'),
        db.CheckConstraint("severity IN ('info','warning','critical')", name='ck_notificacao_severity'),
    )
    id = db.Column(db.Integer, primary_key=True)
    event_key = db.Column(db.String(160), nullable=False, unique=True)
    produto_id = db.Column(db.Integer, db.ForeignKey('produto.id', ondelete='CASCADE'), nullable=False, index=True)
    loja_id = db.Column(db.Integer, db.ForeignKey('loja.id', ondelete='CASCADE'), nullable=False)
    setor_id = db.Column(db.Integer, db.ForeignKey('setor.id', ondelete='CASCADE'), nullable=False)
    kind = db.Column(db.String(30), nullable=False)
    severity = db.Column(db.String(10), nullable=False)
    mensagem = db.Column(db.Text, nullable=False)
    timestamp = db.Column(UTCDateTime(), nullable=False, default=utcnow)
    resolved_at = db.Column(UTCDateTime())
    produto = db.relationship('Produto', lazy='joined')


class NotificationRead(db.Model):
    __tablename__ = 'notificacao_lida'
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id', ondelete='CASCADE'), primary_key=True)
    notificacao_id = db.Column(db.Integer, db.ForeignKey('notificacao.id', ondelete='CASCADE'), primary_key=True)
    read_at = db.Column(UTCDateTime(), nullable=False, default=utcnow)


class JobState(db.Model):
    __tablename__ = 'job_state'
    name = db.Column(db.String(80), primary_key=True)
    last_success_at = db.Column(UTCDateTime())


class ExternalLookupCache(db.Model):
    """Cache técnico com expiração; não é um catálogo editável pelo usuário."""
    __tablename__ = 'external_lookup_cache'
    key = db.Column(db.String(64), primary_key=True)
    payload = db.Column(db.JSON, nullable=False)
    expires_at = db.Column(UTCDateTime(), nullable=False, index=True)


class ApiBudget(db.Model):
    __tablename__ = 'api_budget'
    name = db.Column(db.String(30), primary_key=True)
    next_allowed_at = db.Column(UTCDateTime(), nullable=False)


class Movimento(db.Model):
    __table_args__ = (
        db.CheckConstraint('quantidade > 0', name='ck_movimento_quantidade'),
        db.CheckConstraint("tipo IN ('venda','descarte','devolucao')", name='ck_movimento_tipo'),
        db.CheckConstraint('custo_unitario IS NULL OR custo_unitario >= 0', name='ck_movimento_custo'),
        db.CheckConstraint('valor_unitario IS NULL OR valor_unitario >= 0', name='ck_movimento_valor'),
    )
    id = db.Column(db.Integer, primary_key=True)
    produto_id = db.Column(db.Integer, db.ForeignKey('produto.id', ondelete='RESTRICT'), nullable=False, index=True)
    request_key = db.Column(db.String(64), nullable=False, unique=True)
    tipo = db.Column(db.String(15), nullable=False)
    quantidade = db.Column(db.Integer, nullable=False)
    custo_unitario = db.Column(db.Numeric(12, 2))
    valor_unitario = db.Column(db.Numeric(12, 2))
    motivo = db.Column(db.String(255), nullable=False)
    actor = db.Column(db.String(254), nullable=False)
    timestamp = db.Column(UTCDateTime(), nullable=False, default=utcnow, index=True)


class AuditEvent(db.Model):
    __tablename__ = 'audit_event'
    id = db.Column(db.Integer, primary_key=True)
    produto_id = db.Column(db.Integer, nullable=False, index=True)
    loja_id = db.Column(db.Integer, nullable=False, index=True)
    setor_id = db.Column(db.Integer, nullable=False)
    actor = db.Column(db.String(254), nullable=False)
    action = db.Column(db.String(30), nullable=False)
    changes = db.Column(db.JSON, nullable=False)
    timestamp = db.Column(UTCDateTime(), nullable=False, default=utcnow, index=True)


class LoginLimit(db.Model):
    __tablename__ = 'login_limit'
    key = db.Column(db.String(64), primary_key=True)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    expires_at = db.Column(UTCDateTime(), nullable=False, index=True)


class ExposureProof(db.Model):
    __tablename__ = 'exposure_proof'
    __table_args__ = (
        db.UniqueConstraint('produto_id','revision','image_sha',name='uq_exposure_image'),
        db.CheckConstraint('length(image_data) <= 524288',name='ck_exposure_size'),
        db.Index('ix_exposure_current','produto_id','revision'),
    )
    id = db.Column(db.Integer,primary_key=True)
    produto_id = db.Column(db.Integer,db.ForeignKey('produto.id',ondelete='RESTRICT'),nullable=False)
    revision = db.Column(db.Integer,nullable=False)
    actor = db.Column(db.String(254),nullable=False)
    note = db.Column(db.String(255),nullable=False)
    quantidade = db.Column(db.Integer,nullable=False)
    validade = db.Column(db.Date,nullable=False)
    timestamp = db.Column(UTCDateTime(),nullable=False,default=utcnow)
    image_sha = db.Column(db.String(64),nullable=False)
    image_data = db.deferred(db.Column(db.LargeBinary,nullable=False))
