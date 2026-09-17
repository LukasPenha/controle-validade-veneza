import os
from flask import Flask, request, jsonify, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user
from flask_bcrypt import Bcrypt
from flask_apscheduler import APScheduler
from flask_migrate import Migrate
from dotenv import load_dotenv
from flask_wtf.csrf import CSRFProtect
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import event
from sqlalchemy.engine import Engine
import sqlite3


@event.listens_for(Engine, 'connect')
def sqlite_foreign_keys(connection, record):
    if isinstance(connection, sqlite3.Connection):
        cursor = connection.cursor()
        cursor.execute('PRAGMA foreign_keys=ON')
        cursor.close()

# Carrega as variáveis do arquivo .env
load_dotenv()

db = SQLAlchemy()
bcrypt = Bcrypt()
login_manager = LoginManager()
csrf = CSRFProtect()
migrate = Migrate()

login_manager.login_view = 'auth.login'
login_manager.login_message = 'Por favor, faça login para acessar esta página.'
login_manager.login_message_category = 'info'

def create_app(config=None):
    app = Flask(__name__, instance_relative_config=True)

    # Agora a chave vem do arquivo .env (muito mais seguro)
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
    
    # Pega a URL do banco do arquivo .env
    database_url = os.getenv('DATABASE_URL')
    
    if config:
        database_url = config.get('SQLALCHEMY_DATABASE_URI', database_url)

    # Tratamento de erro caso a pessoa esqueça de criar o .env
    if not database_url:
        raise RuntimeError("ERRO CRÍTICO: Variável DATABASE_URL não encontrada. Crie o arquivo .env!")

    # Correção automática para o SQLAlchemy (caso venha postgres://)
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
        
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=os.getenv('COOKIE_SECURE', 'false').lower() == 'true',
        MAX_CONTENT_LENGTH=8 * 1024 * 1024,
        SCHEDULER_ENABLED=os.getenv('SCHEDULER_ENABLED', 'false').lower() == 'true',
        PUBLIC_BASE_URL=os.getenv('PUBLIC_BASE_URL', ''),
        MAIL_SERVER=os.getenv('MAIL_SERVER', ''),
        MAIL_PORT=int(os.getenv('MAIL_PORT', '587')),
        MAIL_USE_TLS=os.getenv('MAIL_USE_TLS', 'true').lower() == 'true',
        MAIL_USE_SSL=os.getenv('MAIL_USE_SSL', 'false').lower() == 'true',
        MAIL_USERNAME=os.getenv('MAIL_USERNAME', ''),
        MAIL_PASSWORD=os.getenv('MAIL_PASSWORD', ''),
        MAIL_DEFAULT_SENDER=os.getenv('MAIL_DEFAULT_SENDER', ''),
        MAIL_TRANSPORT=os.getenv('MAIL_TRANSPORT', 'smtp'),
        GMAIL_CLIENT_ID=os.getenv('GMAIL_CLIENT_ID', ''),
        GMAIL_CLIENT_SECRET=os.getenv('GMAIL_CLIENT_SECRET', ''),
        GMAIL_REFRESH_TOKEN=os.getenv('GMAIL_REFRESH_TOKEN', ''),
        LOGIN_IP_LIMIT_ENABLED=os.getenv('LOGIN_IP_LIMIT_ENABLED', 'false').lower() == 'true',
        PRODUCT_API_USER_AGENT=os.getenv('PRODUCT_API_USER_AGENT', 'VenezaValidade/2.0 (https://controle-validade-veneza-1.onrender.com)'),
    )
    if config:
        app.config.update(config)
    secret = app.config.get('SECRET_KEY')
    if not secret or len(secret) < 32 or secret == 'chave-padrao-insegura':
        raise RuntimeError('Configure SECRET_KEY com uma chave aleatória de pelo menos 32 caracteres.')

    csrf.init_app(app)
    @app.errorhandler(413)
    def upload_too_large(error):
        return 'Arquivo muito grande. Volte e escolha uma foto de até 6 MB.', 413

    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    

    from .routes import routes
    from . import audit
    from .inventory import inventory_bp
    app.register_blueprint(inventory_bp)
    from .auth import auth_bp
    
    app.register_blueprint(routes)
    app.register_blueprint(auth_bp)
    from .preferences import profile_bp, process_email_jobs
    app.register_blueprint(profile_bp)
    from .product_lookup import lookup_bp
    from .lots import lots_bp
    from .notifications import notifications_bp, unread_query
    app.register_blueprint(lookup_bp)
    app.register_blueprint(lots_bp)
    app.register_blueprint(notifications_bp)
    from .database import register_database_commands
    register_database_commands(app)
    from .access import register_access
    register_access(app)

    @login_manager.unauthorized_handler
    def unauthorized():
        if request.path.startswith('/api/'):
            return jsonify(error='Sua sessão expirou. Entre novamente.'), 401
        return redirect(url_for('auth.login'))

    @app.cli.command('send-emails')
    def send_emails_command():
        """Processa e-mails pendentes; execute a cada minuto em um único processo."""
        process_email_jobs(app)

    if app.config['SCHEDULER_ENABLED'] and not app.testing:
        from .tasks import verificar_validades_diarias
        scheduler = APScheduler()
        scheduler.init_app(app)
        scheduler.add_job(id='validity_check', func=verificar_validades_diarias,
                          args=[app], trigger='interval', minutes=5, max_instances=1, coalesce=True)
        scheduler.add_job(id='email_delivery', func=process_email_jobs, args=[app],
                          trigger='interval', minutes=1, max_instances=1, coalesce=True)
        scheduler.start()

    @app.after_request
    def security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        if current_user.is_authenticated or request.blueprint in ('auth', 'profile'):
            response.headers['Cache-Control'] = 'no-store'
        if request.endpoint in ('auth.reset_password', 'profile.verify'):
            response.headers['Referrer-Policy'] = 'no-referrer'
        return response

    # Injetor de notificações
    @app.context_processor
    def inject_notifications():
        if current_user.is_authenticated:
            try:
                unread_count = unread_query(current_user).count()
                return dict(unread_notification_count=unread_count)
            except SQLAlchemyError:
                db.session.rollback()
                app.logger.exception('Falha ao consultar notificações')
                return dict(unread_notification_count=0)
        return dict(unread_notification_count=0)


    # --- NOVO: Filtro para formatar datas no HTML ---
    @app.template_filter('data_br')
    def data_br_filter(value):
        if not value:
            return ""
        # Formata para Dia/Mês/Ano Hora:Minuto
        from .models import BRASIL
        return value.astimezone(BRASIL).strftime('%d/%m/%Y %H:%M')
    
    @app.template_filter('data_simples')
    def data_simples_filter(value):
        if not value:
            return ""
        # Formata apenas Dia/Mês/Ano
        return value.strftime('%d/%m/%Y')

    @app.template_filter('reais')
    def reais(value):
        if value is None:
            return 'Não informado'
        return 'R$ ' + f'{value:,.2f}'.replace(',', '_').replace('.', ',').replace('_', '.')
    # ------------------------------------------------

    return app
