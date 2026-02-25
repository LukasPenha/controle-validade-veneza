from . import db, bcrypt, login_manager
from flask_login import UserMixin
from datetime import datetime
import pytz  # <--- IMPORTANTE: Import novo

# Função auxiliar para pegar a hora certa
def agora_brasil():
    timezone = pytz.timezone('America/Sao_Paulo')
    return datetime.now(timezone)

@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))

notificacao_lida = db.Table('notificacao_lida',
    db.Column('usuario_id', db.Integer, db.ForeignKey('usuario.id'), primary_key=True),
    db.Column('notificacao_id', db.Integer, db.ForeignKey('notificacao.id'), primary_key=True)
)

class Loja(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), unique=True, nullable=False)
    cnpj = db.Column(db.String(18), nullable=True)
    endereco = db.Column(db.String(255))
    cidade = db.Column(db.String(100))
    estado = db.Column(db.String(2))
    usuarios = db.relationship('Usuario', backref='loja', lazy=True)
    produtos = db.relationship('Produto', backref='loja', lazy=True)
    def __repr__(self):
        return f'<Loja {self.nome}>'

class Setor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(50), unique=True, nullable=False)
    produtos = db.relationship('Produto', backref='setor', lazy=True)
    usuarios = db.relationship('Usuario', backref='setor', lazy=True)
    def __repr__(self):
        return f'<Setor {self.nome}>'

class ProdutoCatalogo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome_produto = db.Column(db.String(200), unique=True, nullable=False)
    plu = db.Column(db.String(50), unique=True, nullable=True)
    barcode_1 = db.Column(db.String(50), nullable=True)
    barcode_2 = db.Column(db.String(50), nullable=True)
    barcode_3 = db.Column(db.String(50), nullable=True)
    def __repr__(self):
        return f'<Catalogo {self.nome_produto}>'

class Usuario(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(50), nullable=False, default='auxiliar_gestao')
    loja_id = db.Column(db.Integer, db.ForeignKey('loja.id'), nullable=True)
    setor_id = db.Column(db.Integer, db.ForeignKey('setor.id'), nullable=True)
    produtos_criados = db.relationship('Produto', backref='criado_por', lazy=True, cascade="all, delete-orphan")
    notificacoes_lidas = db.relationship('Notificacao', secondary=notificacao_lida, back_populates='lido_por', lazy='dynamic')

    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)
    @property
    def nome_display(self):
        if '@' in self.username:
            return self.username.split('@')[0].capitalize()
        return self.username
    def __repr__(self):
        return f'<Usuario {self.username}>'

class Produto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome_produto = db.Column(db.String(200), nullable=False)
    plu = db.Column(db.String(50), nullable=False)
    quantidade = db.Column(db.Integer, nullable=False)
    validade = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(50), nullable=False, default='Para Rebaixa')
    
    # --- MUDANÇA AQUI: Usa agora_brasil em vez de utcnow ---
    data_cadastro = db.Column(db.DateTime, nullable=False, default=agora_brasil)
    # -------------------------------------------------------

    motivo_rebaixa = db.Column(db.String(255), nullable=True)
    loja_id = db.Column(db.Integer, db.ForeignKey('loja.id'), nullable=False)
    setor_id = db.Column(db.Integer, db.ForeignKey('setor.id'), nullable=False)
    criado_por_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=True)
    def __repr__(self):
        return f'<Produto {self.nome_produto}>'

class Notificacao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    loja_id = db.Column(db.Integer, db.ForeignKey('loja.id'), nullable=False)
    mensagem = db.Column(db.String(255), nullable=False)
    
    # --- MUDANÇA AQUI: Usa agora_brasil em vez de utcnow ---
    timestamp = db.Column(db.DateTime, nullable=False, default=agora_brasil)
    # -------------------------------------------------------

    lido_por = db.relationship('Usuario', secondary=notificacao_lida, back_populates='notificacoes_lidas', lazy='dynamic')
    def __repr__(self):
        return f'<Notificacao {self.mensagem}>'