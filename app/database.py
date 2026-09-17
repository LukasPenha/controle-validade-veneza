"""Comandos de instalação para banco novo; nenhum comando apaga tabelas."""
import click
from flask_migrate import upgrade
from sqlalchemy import inspect
from . import db
from .models import Loja, Setor, Usuario


def register_database_commands(app):
    @app.cli.command('init-db')
    def init_db():
        """Instala o esquema versionado somente em um banco vazio."""
        if inspect(db.engine).get_table_names():
            raise click.ClickException('O banco não está vazio. Configure DATABASE_URL para o banco NOVO.')
        upgrade()
        click.echo('Esquema novo instalado. Execute create-admin para criar o primeiro acesso.')

    @app.cli.command('create-admin')
    @click.option('--email', prompt='E-mail do gerente geral')
    @click.password_option(confirmation_prompt=True)
    def create_admin(email, password):
        """Cria o primeiro gerente geral, sem senha fixa ou publicada no Git."""
        from .preferences import valid_email
        try:
            email = valid_email(email)
        except ValueError as error:
            raise click.ClickException(str(error)) from None
        if len(password) < 10 or len(password.encode()) > 72:
            raise click.ClickException('Use pelo menos 10 caracteres e no máximo 72 bytes.')
        if Usuario.query.filter_by(role='gerente_geral').first():
            raise click.ClickException('Já existe um gerente geral. Crie os demais usuários pelo sistema.')
        admin = Usuario(username=email, role='gerente_geral')
        admin.set_password(password)
        db.session.add(admin)
        for name in ('Padaria', 'Açougue', 'Frios', 'Mercearia'):
            if not Setor.query.filter_by(nome=name).first():
                db.session.add(Setor(nome=name))
        db.session.commit()
        click.echo('Gerente geral criado. Entre no sistema para cadastrar suas lojas e equipe.')

    @app.cli.command('process-notifications')
    def process_notifications():
        """Executa alertas internos e e-mails; pode ser agendado externamente."""
        from .notifications import sync_expiry_notifications
        from .preferences import process_email_jobs
        sync_expiry_notifications()
        process_email_jobs(app)
