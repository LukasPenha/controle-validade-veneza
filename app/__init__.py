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
        MAX_CONTENT_LENGTH=1024 * 1024,
        SCHEDULER_ENABLED=os.getenv('SCHEDULER_ENABLED', 'true').lower() == 'true',
        PUBLIC_BASE_URL=os.getenv('PUBLIC_BASE_URL', ''),
        MAIL_SERVER=os.getenv('MAIL_SERVER', ''),
        MAIL_PORT=int(os.getenv('MAIL_PORT', '587')),
        MAIL_USE_TLS=os.getenv('MAIL_USE_TLS', 'true').lower() == 'true',
        MAIL_USE_SSL=os.getenv('MAIL_USE_SSL', 'false').lower() == 'true',
        MAIL_USERNAME=os.getenv('MAIL_USERNAME', ''),
        MAIL_PASSWORD=os.getenv('MAIL_PASSWORD', ''),
        MAIL_DEFAULT_SENDER=os.getenv('MAIL_DEFAULT_SENDER', ''),
    )
    if config:
        app.config.update(config)
    secret = app.config.get('SECRET_KEY')
    if not secret or len(secret) < 32 or secret == 'chave-padrao-insegura':
        raise RuntimeError('Configure SECRET_KEY com uma chave aleatória de pelo menos 32 caracteres.')

    csrf.init_app(app)
    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    

    from .routes import routes
    from .auth import auth_bp
    
    app.register_blueprint(routes)
    app.register_blueprint(auth_bp)
    from .preferences import profile_bp, process_email_jobs
    app.register_blueprint(profile_bp)
    from .catalog_api import catalog_api
    app.register_blueprint(catalog_api)

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
        scheduler.add_job(
            id='daily_validity_check', func=verificar_validades_diarias,
            args=[app], trigger='cron', hour=8, minute=0,
            timezone='America/Sao_Paulo',
        )
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
        return value.strftime('%d/%m/%Y %H:%M')
    
    @app.template_filter('data_simples')
    def data_simples_filter(value):
        if not value:
            return ""
        # Formata apenas Dia/Mês/Ano
        return value.strftime('%d/%m/%Y')
    # ------------------------------------------------

    return app
