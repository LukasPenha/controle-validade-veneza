from flask import Blueprint, current_app, jsonify, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from . import bcrypt
from .models import Usuario, db, utcnow
from datetime import timedelta
from sqlalchemy import func
from .preferences import (EmailDelivery, valid_email, issue_token,
                          find_token, claim_token)

auth_bp = Blueprint('auth', __name__)
_dummy_hash = None


def check_login(user, password):
    """Roda o bcrypt mesmo sem usuário, para o tempo de resposta não revelar quem existe."""
    global _dummy_hash
    if not password or len(password.encode()) > 72:
        return False
    if user:
        return user.check_password(password)
    if _dummy_hash is None:
        _dummy_hash = bcrypt.generate_password_hash('senha-ficticia-para-tempo-constante').decode()
    bcrypt.check_password_hash(_dummy_hash, password)
    return False


def register_session_timeout(app):
    """Encerra a sessão após SESSION_IDLE_MINUTES sem uso ou PERMANENT_SESSION_LIFETIME após o login."""
    @app.before_request
    def expire_idle_session():
        if not current_user.is_authenticated or request.endpoint == 'static':
            return None
        now = int(utcnow().timestamp())
        last_seen = session.setdefault('last_seen', now)
        login_at = session.setdefault('login_at', now)
        idle = now - last_seen > app.config['SESSION_IDLE_MINUTES'] * 60
        too_old = now - login_at > app.config['PERMANENT_SESSION_LIFETIME'].total_seconds()
        if idle or too_old:
            logout_user()
            session.clear()
            if request.path.startswith('/api/'):
                return jsonify(error='Sua sessão expirou. Entre novamente.'), 401
            flash('Sua sessão expirou. Entre novamente.', 'info')
            return redirect(url_for('auth.login'))
        if now - last_seen >= 60:
            session['last_seen'] = now
        return None

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        # Redireciona para a rota principal, que decidirá o dashboard correto
        return redirect(url_for('routes.index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip().lower()
        password = request.form.get('password', '')
        from .login_protection import allow_attempt
        if not allow_attempt(username):
            flash('Muitas tentativas. Aguarde 15 minutos antes de tentar novamente.', 'warning')
            return render_template('login.html'), 429, {'Retry-After': '900'}
        user = Usuario.query.filter(func.lower(Usuario.username) == username).first()

        if check_login(user, password):
            session.clear()
            session.permanent = True
            session['login_at'] = session['last_seen'] = int(utcnow().timestamp())
            login_user(user)
            flash('Login realizado com sucesso!', 'success')
            # Redireciona para a rota principal após o login
            return redirect(url_for('routes.index'))
        else:
            flash('Usuário ou senha inválidos.', 'danger')

    return render_template('login.html')

@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    flash('Você foi desconectado.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/esqueci-senha', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        try:
            address = valid_email(request.form.get('email'))
        except ValueError:
            address = None
        user = address and Usuario.query.filter(func.lower(Usuario.username) == address).first()
        if user:
            recent = EmailDelivery.query.filter_by(user_id=user.id, kind='reset').filter(
                EmailDelivery.created_at > utcnow() - timedelta(minutes=5)).first()
            if not recent:
                try:
                    issue_token(user, 'reset', address)
                    db.session.commit()
                except ValueError:
                    # Erro de configuração (ex.: PUBLIC_BASE_URL sem HTTPS): o e-mail não sai.
                    db.session.rollback()
                    current_app.logger.exception('Falha ao gerar o link de redefinição de senha')
        flash('Se houver uma conta com esse e-mail, enviaremos um link para redefinir a senha. '
              'Verifique também a pasta de spam.', 'info')
        return redirect(url_for('auth.forgot_password'))
    return render_template('auth_action.html', mode='forgot', valid=True)


@auth_bp.route('/redefinir-senha/<token>', methods=['GET', 'POST'])
def reset_password(token):
    record = find_token(token, 'reset')
    if record and request.method == 'POST':
        password = request.form.get('password', '')
        if len(password) < 10 or len(password.encode('utf-8')) > 72:
            flash('Use pelo menos 10 caracteres e no máximo 72 bytes na senha.', 'danger')
        elif password != request.form.get('confirmation'):
            flash('As senhas não coincidem.', 'danger')
        elif claim_token(record):
            user = db.session.get(Usuario, record.user_id)
            user.set_password(password)
            db.session.commit()
            session.clear()
            flash('Senha atualizada. Entre com sua nova senha.', 'success')
            return redirect(url_for('auth.login'))
        else:
            db.session.rollback()
            record = None
    return render_template('auth_action.html', mode='reset', valid=bool(record))

# A rota de criar usuário foi movida para routes.py e agora é parte do
# gerenciamento do Gerente Geral, então não precisamos mais dela aqui.
