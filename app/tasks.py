from flask import render_template
from flask_mail import Message
from collections import defaultdict
from datetime import date, timedelta
from . import db, create_app
from .models import Produto, Usuario, Notificacao

def criar_notificacao_task(loja_id, mensagem):
    """Função auxiliar para adicionar notificação a partir de uma task."""
    if loja_id:
        nova_notificacao = Notificacao(loja_id=loja_id, mensagem=mensagem)
        db.session.add(nova_notificacao)

def verificar_validades_diarias():
    """
    Verifica produtos que venceram hoje ou que entrarão no período crítico
    e cria notificações no banco de dados para a loja correspondente.
    """
    app = create_app()
    with app.app_context():
        print("Iniciando tarefa diária de verificação de validades...")
        
        # Produtos que venceram HOJE
        produtos_vencidos_hoje = Produto.query.filter(Produto.validade == date.today()).all()
        for produto in produtos_vencidos_hoje:
            msg = f"PRODUTO VENCIDO: '{produto.nome_produto}' venceu hoje."
            criar_notificacao_task(produto.loja_id, msg)

        # Produtos que entrarão no período crítico (vencem em 3 dias)
        data_limite_critico = date.today() + timedelta(days=3)
        produtos_criticos = Produto.query.filter(Produto.validade == data_limite_critico).all()
        for produto in produtos_criticos:
            msg = f"ALERTA: '{produto.nome_produto}' vence em 3 dias."
            criar_notificacao_task(produto.loja_id, msg)
            
        db.session.commit()
        print("Tarefa de verificação de validades concluída.")