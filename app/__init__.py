import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user
from flask_bcrypt import Bcrypt
from flask_apscheduler import APScheduler
from flask_migrate import Migrate
from dotenv import load_dotenv  # <--- IMPORT NOVO

# Carrega as variáveis do arquivo .env
load_dotenv()

db = SQLAlchemy()
bcrypt = Bcrypt()
login_manager = LoginManager()
scheduler = APScheduler()
migrate = Migrate()

login_manager.login_view = 'auth.login'
login_manager.login_message = 'Por favor, faça login para acessar esta página.'
login_manager.login_message_category = 'info'

def create_app():
    app = Flask(__name__, instance_relative_config=True)

    # Agora a chave vem do arquivo .env (muito mais seguro)
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'chave-padrao-insegura')
    
    # Pega a URL do banco do arquivo .env
    database_url = os.getenv('DATABASE_URL')
    
    # Tratamento de erro caso a pessoa esqueça de criar o .env
    if not database_url:
        raise RuntimeError("ERRO CRÍTICO: Variável DATABASE_URL não encontrada. Crie o arquivo .env!")

    # Correção automática para o SQLAlchemy (caso venha postgres://)
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
        
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    
    scheduler.init_app(app)
    scheduler.start()

    from .routes import routes
    from .auth import auth_bp
    
    app.register_blueprint(routes)
    app.register_blueprint(auth_bp)

    from . import tasks
    if not scheduler.get_job('daily_validity_check'):
        scheduler.add_job(id='daily_validity_check', func=tasks.verificar_validades_diarias, trigger='cron', hour=8, minute=0)

    # Injetor de notificações
    from .models import Notificacao, notificacao_lida
    @app.context_processor
    def inject_notifications():
        if current_user.is_authenticated and hasattr(current_user, 'loja_id') and current_user.loja_id:
            try:
                lidas_subquery = db.session.query(notificacao_lida.c.notificacao_id).filter_by(usuario_id=current_user.id)
                unread_count = Notificacao.query.filter(
                    Notificacao.loja_id == current_user.loja_id,
                    ~Notificacao.id.in_(lidas_subquery)
                ).count()
                return dict(unread_notification_count=unread_count)
            except:
                return dict(unread_notification_count=0)
        return dict(unread_notification_count=0)

# ... (código anterior) ...

    # --- NOVO: Filtro para formatar datas no HTML ---
    @app.template_filter('data_br')
    def data_br_filter(value):
        if not value:
            return ""
        # Formata para Dia/Mês/Ano Hora:Minuto
        return value.strftime('%d/%m/%Y %H:%M')
    
    @app.template_filter('data_simples')
    def data_simples_filter(value):
        if not value:
            return ""
        # Formata apenas Dia/Mês/Ano
        return value.strftime('%d/%m/%Y')
    # ------------------------------------------------

    return app