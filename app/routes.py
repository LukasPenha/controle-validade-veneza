from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, Response
from flask_login import login_required, current_user
from .models import db, Produto, Usuario, Loja, Setor, ProdutoCatalogo, Notificacao
from datetime import datetime, date, time, timedelta
from sqlalchemy import cast, Date, or_, func
import io
import requests
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch

routes = Blueprint('routes', __name__)

# --- FUNÇÃO HELPER PARA CRIAR NOTIFICAÇÕES ---
def criar_notificacao(loja_id, mensagem):
    if loja_id:
        nova_notificacao = Notificacao(loja_id=loja_id, mensagem=mensagem)
        db.session.add(nova_notificacao)

# --- FUNÇÃO HELPER PARA DESENHAR O PDF (ATUALIZADA) ---
def draw_pdf_report(buffer, titulo_principal, subtitulo, lista_produtos, is_geral=False):
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    
    # Cabeçalho do Relatório
    p.setTitle(titulo_principal)
    p.setFont("Helvetica-Bold", 12)
    p.drawString(inch, height - inch, titulo_principal)
    
    p.setFont("Helvetica", 10)
    p.drawString(inch, height - inch - 20, subtitulo)
    
    y = height - inch - 60
    p.setFont("Helvetica-Bold", 8) # Fonte menor para caber tudo
    
    # --- DEFINIÇÃO DAS COLUNAS ---
    if is_geral:
        # Layout Geral: Loja | Produto | PLU | Qtd | Validade | Quem Cadastrou
        headers = ["Loja", "Descrição (Produto)", "PLU", "Qtd", "Validade", "Quem Cadastrou"]
        # Posições X (ajustadas para paisagem ou letra apertada)
        col_positions = [inch, inch + 70, inch + 220, inch + 270, inch + 300, inch + 360]
    else:
        # Layout Local: Produto | PLU | Qtd | Validade | Status | Quem Cadastrou
        headers = ["Descrição (Produto)", "PLU", "Qtd", "Validade", "Status", "Quem Cadastrou"]
        col_positions = [inch, inch + 180, inch + 230, inch + 260, inch + 320, inch + 400]
    
    # Desenha os títulos das colunas
    for i, header in enumerate(headers):
        p.drawString(col_positions[i], y, header)
    
    y -= 5
    p.line(inch, y, width - inch, y) # Linha separadora
    y -= 15
    
    p.setFont("Helvetica", 8)
    
    if not lista_produtos:
        p.drawString(inch, y, "Nenhum produto encontrado para os filtros selecionados.")
    else:
        for produto in lista_produtos:
            # Verifica se precisa de nova página
            if y < inch:
                p.showPage()
                y = height - inch - 20
                p.setFont("Helvetica-Bold", 8)
                p.drawString(inch, y, "Continuação...")
                y -= 25
                p.setFont("Helvetica", 8)

            # Desenha os dados
            if is_geral:
                p.drawString(col_positions[0], y, produto.get('loja', '')[:12])
                p.drawString(col_positions[1], y, produto.get('nome_produto', '')[:28]) # Trunca nome longo
                p.drawString(col_positions[2], y, str(produto.get('plu', '')))
                p.drawString(col_positions[3], y, str(produto.get('quantidade', '')))
                p.drawString(col_positions[4], y, produto.get('validade', ''))
                p.drawString(col_positions[5], y, produto.get('criado_por', '')[:20])
            else:
                p.drawString(col_positions[0], y, produto.get('nome_produto', '')[:35]) # Trunca nome longo
                p.drawString(col_positions[1], y, str(produto.get('plu', '')))
                p.drawString(col_positions[2], y, str(produto.get('quantidade', '')))
                p.drawString(col_positions[3], y, produto.get('validade', ''))
                p.drawString(col_positions[4], y, produto.get('status', '')[:12])
                p.drawString(col_positions[5], y, produto.get('criado_por', '')[:25])
            
            y -= 12 # Espaçamento entre linhas
            
    p.showPage()
    p.save()

# --- ROTA PRINCIPAL E DASHBOARDS ---
@routes.route('/')
def index():
    if not current_user.is_authenticated: return redirect(url_for('auth.login'))
    role_dashboard_map = {
        'gerente_geral': 'routes.dashboard_gerente_geral', 
        'gerente_trocas': 'routes.dashboard_gerente_trocas',
        'gerente': 'routes.produtos_para_rebaixa',
        'encarregado_setor': 'routes.listar_produtos_encarregado',
        'auxiliar_gestao': 'routes.dashboard_auxiliar'
    }
    dashboard_route = role_dashboard_map.get(current_user.role)
    if dashboard_route: return redirect(url_for(dashboard_route))
    flash('Seu cargo ainda não possui um dashboard definido.', 'info')
    return redirect(url_for('auth.login'))

@routes.route('/notifications')
@login_required
def notifications():
    if not hasattr(current_user, 'loja_id') or not current_user.loja_id:
        flash("Este usuário não está associado a uma loja para ver notificações.", "info")
        return redirect(url_for('routes.index'))
    notificacoes_loja = Notificacao.query.filter_by(loja_id=current_user.loja_id).order_by(Notificacao.timestamp.desc()).all()
    notificacoes_nao_lidas = [n for n in notificacoes_loja if current_user not in n.lido_por]
    for notificacao in notificacoes_nao_lidas:
        current_user.notificacoes_lidas.append(notificacao)
    db.session.commit()
    notificacoes_lidas_ids = [n.id for n in current_user.notificacoes_lidas]
    return render_template('geral/notifications.html', notificacoes=notificacoes_loja, notificacoes_lidas_ids=notificacoes_lidas_ids)


# --- ROTAS DO GERENTE GERAL ---

@routes.route('/gerente-geral/dashboard')
@login_required
def dashboard_gerente_geral():
    if current_user.role != 'gerente_geral': 
        return redirect(url_for('routes.index'))
    try:
        total_lojas = Loja.query.count()
        total_usuarios = Usuario.query.filter(Usuario.role != 'gerente_geral').count()
        total_catalogo = ProdutoCatalogo.query.count()
    except Exception as e:
        print(f"Erro ao contar dados: {e}")
        total_lojas = 0; total_usuarios = 0; total_catalogo = 0

    return render_template('geral/dashboard.html', 
                           total_lojas=total_lojas, 
                           total_usuarios=total_usuarios, 
                           total_catalogo=total_catalogo)

@routes.route('/catalogo')
@login_required
def gerenciar_catalogo():
    if current_user.role not in ['gerente_geral', 'gerente']:
        flash('Você não tem permissão para acessar o catálogo.', 'danger')
        return redirect(url_for('routes.index'))
    page = request.args.get('page', 1, type=int)
    catalogo = ProdutoCatalogo.query.order_by(ProdutoCatalogo.nome_produto).paginate(page=page, per_page=15)
    return render_template('geral/gerenciar_catalogo.html', catalogo=catalogo)

@routes.route('/catalogo/adicionar', methods=['GET', 'POST'])
@login_required
def adicionar_catalogo():
    if current_user.role not in ['gerente_geral', 'gerente', 'encarregado_setor', 'auxiliar_gestao']:
        flash('Você não tem permissão para cadastrar novos produtos.', 'danger')
        return redirect(url_for('routes.index'))
    
    if request.method == 'POST':
        nome_produto = request.form.get('nome_produto')
        plu = request.form.get('plu')
        barcode_1 = request.form.get('barcode_1') or None
        barcode_2 = request.form.get('barcode_2') or None
        barcode_3 = request.form.get('barcode_3') or None

        existing_item = ProdutoCatalogo.query.filter(
            or_(func.lower(ProdutoCatalogo.nome_produto) == func.lower(nome_produto), 
                func.lower(ProdutoCatalogo.plu) == func.lower(plu))
        ).first()
        if existing_item:
            flash(f'Já existe um produto com este Nome ou PLU no catálogo.', 'warning')
            return redirect(url_for('routes.adicionar_catalogo'))
        
        barcodes = [b for b in [barcode_1, barcode_2, barcode_3] if b]
        if barcodes:
            existing_barcode = ProdutoCatalogo.query.filter(
                or_(
                    ProdutoCatalogo.barcode_1.in_(barcodes),
                    ProdutoCatalogo.barcode_2.in_(barcodes),
                    ProdutoCatalogo.barcode_3.in_(barcodes)
                )
            ).first()
            if existing_barcode:
                flash(f'Um dos códigos de barras fornecidos já está em uso no produto "{existing_barcode.nome_produto}".', 'warning')
                return redirect(url_for('routes.adicionar_catalogo'))

        novo_item = ProdutoCatalogo(
            nome_produto=nome_produto, plu=plu,
            barcode_1=barcode_1, barcode_2=barcode_2, barcode_3=barcode_3
        )
        db.session.add(novo_item)
        db.session.commit()
        flash(f'Produto "{nome_produto}" adicionado ao catálogo com sucesso!', 'success')
        return redirect(url_for('routes.gerenciar_catalogo'))
        
    return render_template('geral/cadastrar_catalogo.html')

@routes.route('/catalogo/editar/<int:item_id>', methods=['POST'])
@login_required
def editar_catalogo(item_id):
    if current_user.role not in ['gerente_geral', 'gerente']:
        flash('Você não tem permissão para editar o catálogo.', 'danger')
        return redirect(url_for('routes.gerenciar_catalogo'))
    item = ProdutoCatalogo.query.get_or_404(item_id)
    item.nome_produto = request.form.get('nome_produto')
    item.plu = request.form.get('plu')
    item.barcode_1 = request.form.get('barcode_1') or None
    item.barcode_2 = request.form.get('barcode_2') or None
    item.barcode_3 = request.form.get('barcode_3') or None
    db.session.commit()
    flash(f'Item "{item.nome_produto}" atualizado com sucesso!', 'success')
    return redirect(url_for('routes.gerenciar_catalogo'))

@routes.route('/catalogo/excluir/<int:item_id>', methods=['POST'])
@login_required
def excluir_catalogo(item_id):
    if current_user.role not in ['gerente_geral', 'gerente']:
        flash('Você não tem permissão para excluir do catálogo.', 'danger')
        return redirect(url_for('routes.gerenciar_catalogo'))
    item = ProdutoCatalogo.query.get_or_404(item_id)
    db.session.delete(item)
    db.session.commit()
    flash(f'Item "{item.nome_produto}" excluído do catálogo.', 'success')
    return redirect(url_for('routes.gerenciar_catalogo'))

@routes.route('/gerente-geral/relatorio', methods=['GET'])
@login_required
def relatorio_gerente_geral():
    if current_user.role != 'gerente_geral': return redirect(url_for('routes.index'))
    lojas = Loja.query.order_by(Loja.nome).all()
    return render_template('geral/relatorio.html', lojas=lojas)

@routes.route('/gerente-geral/lojas', methods=['GET', 'POST'])
@login_required
def gerenciar_lojas():
    if current_user.role != 'gerente_geral': return redirect(url_for('routes.index'))
    if request.method == 'POST':
        nome = request.form.get('nome')
        cnpj = request.form.get('cnpj') or None
        if Loja.query.filter(func.lower(Loja.nome) == func.lower(nome)).first():
            flash(f'Uma loja com o nome "{nome}" já existe.', 'warning')
        elif cnpj and Loja.query.filter_by(cnpj=cnpj).first():
            flash(f'Uma loja com o CNPJ "{cnpj}" já existe.', 'warning')
        else:
            nova_loja = Loja(
                nome=nome, 
                cnpj=cnpj, 
                endereco=request.form.get('endereco'), 
                cidade=request.form.get('cidade'), 
                estado=request.form.get('estado')
            )
            db.session.add(nova_loja)
            db.session.commit()
            flash(f'Loja "{nome}" criada com sucesso!', 'success')
        return redirect(url_for('routes.gerenciar_lojas'))
    lojas = Loja.query.order_by(Loja.nome).all()
    return render_template('geral/gerenciar_lojas.html', lojas=lojas)

@routes.route('/gerente-geral/loja/editar/<int:loja_id>', methods=['POST'])
@login_required
def editar_loja(loja_id):
    if current_user.role != 'gerente_geral': return redirect(url_for('routes.index'))
    loja = Loja.query.get_or_404(loja_id)
    loja.nome, loja.cnpj, loja.endereco, loja.cidade, loja.estado = request.form.get('nome'), request.form.get('cnpj') or None, request.form.get('endereco'), request.form.get('cidade'), request.form.get('estado')
    db.session.commit()
    flash('Dados da loja atualizados com sucesso!', 'success')
    return redirect(url_for('routes.gerenciar_lojas'))

@routes.route('/gerente-geral/loja/excluir/<int:loja_id>', methods=['POST'])
@login_required
def excluir_loja(loja_id):
    if current_user.role != 'gerente_geral': return redirect(url_for('routes.index'))
    loja_para_excluir = Loja.query.get_or_404(loja_id)
    if loja_para_excluir.usuarios:
        flash(f'Não é possível excluir a loja "{loja_para_excluir.nome}", pois ela possui usuários vinculados.', 'danger')
    else:
        db.session.delete(loja_para_excluir)
        db.session.commit()
        flash(f'Loja "{loja_para_excluir.nome}" foi excluída com sucesso.', 'success')
    return redirect(url_for('routes.gerenciar_lojas'))

@routes.route('/gerente-geral/usuarios', methods=['GET', 'POST'])
@login_required
def gerenciar_usuarios_geral():
    if current_user.role != 'gerente_geral': return redirect(url_for('routes.index'))
    if request.method == 'POST':
        username = request.form.get('username'); password = request.form.get('password')
        role = request.form.get('role'); loja_id = request.form.get('loja_id'); setor_id = request.form.get('setor_id')

        if Usuario.query.filter(func.lower(Usuario.username) == func.lower(username)).first():
            flash(f'O e-mail "{username}" já está em uso.', 'warning')
        elif role in ['gerente', 'encarregado_setor', 'auxiliar_gestao'] and not loja_id:
            flash('Para este cargo, é obrigatório selecionar uma loja.', 'danger')
        elif role == 'encarregado_setor' and not setor_id:
            flash('Para o cargo de Encarregado de Setor, é obrigatório selecionar um setor.', 'danger')
        else:
            loja_id = int(loja_id) if loja_id else None
            setor_id = int(setor_id) if setor_id else None
            if role == 'gerente_trocas': loja_id = None
            if role != 'encarregado_setor': setor_id = None
            novo_usuario = Usuario(username=username, role=role, loja_id=loja_id, setor_id=setor_id)
            novo_usuario.set_password(password)
            db.session.add(novo_usuario)
            db.session.commit()
            flash(f'Usuário "{username}" criado com sucesso!', 'success')
        return redirect(url_for('routes.gerenciar_usuarios_geral'))

    search_term = request.args.get('search_term', '').lower()
    loja_id_filter = request.args.get('loja_id', '')
    query = Loja.query.order_by(Loja.nome)
    if loja_id_filter: query = query.filter(Loja.id == loja_id_filter)
    if search_term: query = query.join(Usuario).filter(func.lower(Usuario.username).contains(search_term))
    lojas_com_usuarios = query.all()
    todos_usuarios = Usuario.query.filter(Usuario.role != 'gerente_geral').all()
    lojas_para_dropdown = Loja.query.order_by(Loja.nome).all()
    setores = Setor.query.all()
    return render_template('geral/gerenciar_usuarios.html', lojas_com_usuarios=lojas_com_usuarios, todos_usuarios=todos_usuarios, lojas=lojas_para_dropdown, setores=setores)

@routes.route('/gerente-geral/usuario/editar/<int:usuario_id>', methods=['POST'])
@login_required
def editar_usuario(usuario_id):
    if current_user.role != 'gerente_geral': return redirect(url_for('routes.index'))
    usuario = Usuario.query.get_or_404(usuario_id)
    usuario.username = request.form.get('username'); usuario.role = request.form.get('role')
    loja_id = request.form.get('loja_id'); setor_id = request.form.get('setor_id'); new_password = request.form.get('password')

    if usuario.role in ['gerente', 'encarregado_setor', 'auxiliar_gestao'] and not loja_id:
        flash('Para este cargo, é obrigatório selecionar uma loja.', 'danger')
        return redirect(url_for('routes.gerenciar_usuarios_geral'))
    if usuario.role == 'encarregado_setor' and not setor_id:
        flash('Para o cargo de Encarregado de Setor, é obrigatório selecionar um setor.', 'danger')
        return redirect(url_for('routes.gerenciar_usuarios_geral'))

    if new_password: usuario.set_password(new_password)
    usuario.loja_id = int(loja_id) if loja_id and loja_id.isdigit() else None
    usuario.setor_id = int(setor_id) if setor_id and setor_id.isdigit() else None
    if usuario.role == 'gerente_trocas': usuario.loja_id = None
    if usuario.role != 'encarregado_setor': usuario.setor_id = None
    db.session.commit()
    flash('Usuário atualizado com sucesso!', 'success')
    return redirect(url_for('routes.gerenciar_usuarios_geral'))

@routes.route('/gerente-geral/usuario/excluir/<int:usuario_id>', methods=['POST'])
@login_required
def excluir_usuario(usuario_id):
    if current_user.role != 'gerente_geral': return redirect(url_for('routes.index'))
    Produto.query.filter_by(criado_por_id=usuario_id).update({"criado_por_id": None})
    usuario_para_excluir = Usuario.query.get_or_404(usuario_id)
    db.session.delete(usuario_para_excluir)
    db.session.commit()
    flash(f'Usuário "{usuario_para_excluir.username}" foi excluído.', 'success')
    return redirect(url_for('routes.gerenciar_usuarios_geral'))

# --- ROTAS DE CARGOS ---
@routes.route('/gerente/para-rebaixa')
@login_required
def produtos_para_rebaixa():
    if current_user.role != 'gerente': return redirect(url_for('routes.index'))
    page = request.args.get('page', 1, type=int)
    produtos = Produto.query.filter(Produto.loja_id == current_user.loja_id, Produto.status == 'Para Rebaixa', Produto.validade >= date.today()).order_by(Produto.validade.asc()).paginate(page=page, per_page=20)
    return render_template('gerente/produtos_para_rebaixa.html', produtos_para_rebaixa=produtos, now=datetime.now())

@routes.route('/gerente/em-rebaixa')
@login_required
def produtos_em_rebaixa():
    if current_user.role != 'gerente': return redirect(url_for('routes.index'))
    page = request.args.get('page', 1, type=int)
    produtos = Produto.query.filter(Produto.loja_id == current_user.loja_id, Produto.status == 'Em Rebaixa', Produto.validade >= date.today()).order_by(Produto.validade.asc()).paginate(page=page, per_page=20)
    return render_template('gerente/produtos_em_rebaixa.html', produtos_em_rebaixa=produtos, now=datetime.now())

@routes.route('/gerente/relatorio')
@login_required
def relatorio_gerente():
    if current_user.role != 'gerente': return redirect(url_for('routes.index'))
    return render_template('gerente/relatorio.html')

@routes.route('/encarregado/produtos')
@login_required
def listar_produtos_encarregado():
    if current_user.role != 'encarregado_setor': return redirect(url_for('routes.index'))
    page = request.args.get('page', 1, type=int)
    produtos = Produto.query.filter(Produto.loja_id == current_user.loja_id, Produto.setor_id == current_user.setor_id, Produto.validade >= date.today()).order_by(Produto.validade.asc()).paginate(page=page, per_page=20)
    return render_template('encarregado/listar_produtos.html', produtos=produtos, now=datetime.now())

@routes.route('/encarregado/relatorio')
@login_required
def relatorio_encarregado():
    if current_user.role != 'encarregado_setor': return redirect(url_for('routes.index'))
    return render_template('encarregado/relatorio.html')

@routes.route('/encarregado/vencidos')
@login_required
def vencidos_encarregado():
    if current_user.role != 'encarregado_setor': return redirect(url_for('routes.index'))
    page = request.args.get('page', 1, type=int)
    data_limite = date.today() - timedelta(days=30)
    produtos_vencidos = Produto.query.filter(Produto.loja_id == current_user.loja_id, Produto.setor_id == current_user.setor_id, Produto.validade < date.today(), Produto.validade >= data_limite).order_by(Produto.validade.asc()).paginate(page=page, per_page=20)
    return render_template('encarregado/produtos_vencidos.html', produtos=produtos_vencidos, today=date.today())

@routes.route('/auxiliar/dashboard')
@login_required
def dashboard_auxiliar():
    if current_user.role != 'auxiliar_gestao': return redirect(url_for('routes.index'))
    return redirect(url_for('routes.datas_curtas'))

@routes.route('/gerente-trocas/dashboard')
@login_required
def dashboard_gerente_trocas():
    if current_user.role != 'gerente_trocas': return redirect(url_for('routes.index'))
    lojas = Loja.query.order_by(Loja.nome).all()
    setores = Setor.query.order_by(Setor.nome).all()
    return render_template('gerente_trocas/dashboard_trocas.html', lojas=lojas, setores=setores)

@routes.route('/produtos/vencidos')
@login_required
def pagina_produtos_vencidos():
    if current_user.role not in ['gerente', 'gerente_geral', 'gerente_trocas']: return redirect(url_for('routes.index'))
    page = request.args.get('page', 1, type=int)
    data_limite = date.today() - timedelta(days=30)
    query = Produto.query.filter(Produto.validade < date.today(), Produto.validade >= data_limite)
    if current_user.role == 'gerente':
        query = query.filter(Produto.loja_id == current_user.loja_id)
        produtos_vencidos = query.order_by(Produto.validade.asc()).paginate(page=page, per_page=20)
        return render_template('gerente/produtos_vencidos.html', produtos=produtos_vencidos, today=date.today())
    produtos_vencidos = query.order_by(Produto.loja_id, Produto.validade.asc()).paginate(page=page, per_page=20)
    return render_template('geral/produtos_vencidos.html', produtos=produtos_vencidos, today=date.today())

@routes.route('/produtos/bulk-action', methods=['POST'])
@login_required
def bulk_action():
    action = request.form.get('action'); selected_ids = request.form.getlist('selected_ids')
    if not selected_ids:
        flash('Nenhum item selecionado.', 'warning'); return redirect(request.referrer)
    produtos = Produto.query.filter(Produto.id.in_(selected_ids)).all()
    if action == 'delete':
        count = 0
        for produto in produtos:
            if (current_user.role == 'gerente_geral' or (current_user.role == 'gerente' and produto.loja_id == current_user.loja_id) or (current_user.role == 'encarregado_setor' and produto.loja_id == current_user.loja_id and produto.setor_id == current_user.setor_id)):
                db.session.delete(produto); count += 1
        flash(f'{count} produtos foram excluídos.', 'success')
    db.session.commit()
    return redirect(request.referrer)

@routes.route('/produtos/<int:produto_id>/editar', methods=['POST'])
@login_required
def editar_produto(produto_id):
    if current_user.role != 'encarregado_setor': return redirect(url_for('routes.index'))
    produto = Produto.query.get_or_404(produto_id)
    if produto.loja_id != current_user.loja_id or produto.setor_id != current_user.setor_id:
        flash('Você só pode editar produtos do seu setor.', 'danger')
        return redirect(url_for('routes.listar_produtos_encarregado'))
    produto.nome_produto = request.form.get('nome_produto'); produto.plu = request.form.get('plu')
    produto.quantidade = int(request.form.get('quantidade')); produto.validade = datetime.strptime(request.form.get('validade'), '%Y-%m-%d').date()
    produto.motivo_rebaixa = request.form.get('motivo_rebaixa')
    db.session.commit()
    flash('Produto atualizado com sucesso!', 'success')
    return redirect(url_for('routes.listar_produtos_encarregado'))

@routes.route('/produtos/<int:produto_id>/status', methods=['POST'])
@login_required
def alterar_status(produto_id):
    if current_user.role != 'gerente': return redirect(url_for('routes.index'))
    produto = Produto.query.get_or_404(produto_id)
    if produto.loja_id != current_user.loja_id: return redirect(request.referrer)
    novo_status = request.form.get('status')
    if novo_status in ['Para Rebaixa', 'Em Rebaixa']:
        produto.status = novo_status
        mensagem = f"Status de '{produto.nome_produto}' alterado para '{novo_status}' por {current_user.nome_display}."
        criar_notificacao(produto.loja_id, mensagem)
        db.session.commit()
        flash(f'Status do produto {produto.nome_produto} alterado.', 'success')
    else: flash('Status inválido.', 'danger')
    return redirect(request.referrer or url_for('routes.produtos_para_rebaixa'))

@routes.route('/produtos/<int:produto_id>/excluir', methods=['POST'])
@login_required
def excluir_produto(produto_id):
    if current_user.role not in ['encarregado_setor', 'gerente_geral', 'gerente']: return redirect(url_for('routes.index'))
    produto = Produto.query.get_or_404(produto_id)
    if current_user.role == 'encarregado_setor' and (produto.loja_id != current_user.loja_id or produto.setor_id != current_user.setor_id): return redirect(url_for('routes.index'))
    if current_user.role == 'gerente' and produto.loja_id != current_user.loja_id: return redirect(url_for('routes.index'))
    db.session.delete(produto)
    db.session.commit()
    flash('Produto excluído com sucesso!', 'success')
    return redirect(request.referrer or url_for('routes.index'))

# --- ROTAS PARA DATAS CURTAS ---
@routes.route('/datas-curtas')
@login_required
def datas_curtas():
    if current_user.role not in ['gerente', 'encarregado_setor', 'auxiliar_gestao']:
        flash('Você não tem permissão para acessar esta página.', 'danger')
        return redirect(url_for('routes.index'))
    return render_template('geral/datas_curtas.html')

@routes.route('/cadastrar-rebaixa/<int:catalogo_id>')
@login_required
def cadastrar_rebaixa_form(catalogo_id):
    if current_user.role not in ['gerente', 'encarregado_setor', 'auxiliar_gestao']:
        flash('Você não tem permissão para acessar esta página.', 'danger')
        return redirect(url_for('routes.index'))
    catalogo_item = ProdutoCatalogo.query.get_or_404(catalogo_id)
    setores = Setor.query.all() if current_user.role in ['gerente', 'auxiliar_gestao'] else None
    return render_template('geral/cadastrar_rebaixa.html', catalogo_item=catalogo_item, setores=setores)

@routes.route('/cadastrar-rebaixa', methods=['POST'])
@login_required
def cadastrar_rebaixa():
    if current_user.role not in ['gerente', 'encarregado_setor', 'auxiliar_gestao']:
        flash('Você não tem permissão para esta ação.', 'danger')
        return redirect(url_for('routes.index'))
    nome_produto = request.form.get('nome_produto'); plu = request.form.get('plu'); quantidade = request.form.get('quantidade')
    validade_str = request.form.get('validade'); motivo_rebaixa = request.form.get('motivo_rebaixa'); setor_id = request.form.get('setor_id')
    if current_user.role == 'encarregado_setor': setor_id = current_user.setor_id
    if not all([quantidade, validade_str, setor_id]):
        flash('Quantidade, validade e setor são obrigatórios.', 'danger'); return redirect(request.referrer)
    novo_produto = Produto(
        nome_produto=nome_produto, plu=plu, quantidade=int(quantidade),
        validade=datetime.strptime(validade_str, '%Y-%m-%d').date(),
        motivo_rebaixa=motivo_rebaixa, setor_id=int(setor_id),
        loja_id=current_user.loja_id, criado_por_id=current_user.id,
        status='Para Rebaixa'
    )
    db.session.add(novo_produto)
    mensagem = f"Item para rebaixa: {quantidade}x {nome_produto} cadastrado por {current_user.nome_display}."
    criar_notificacao(current_user.loja_id, mensagem)
    db.session.commit()
    flash(f'O produto "{nome_produto}" foi enviado para o painel do gerente para rebaixa.', 'success')
    return redirect(url_for('routes.datas_curtas'))

# --- ROTAS DE API ---
@routes.route('/api/buscar-produtos-catalogo')
@login_required
def api_buscar_produtos_catalogo():
    search_term = request.args.get('term', '')
    if not search_term or len(search_term) < 3: return jsonify([])
    query = ProdutoCatalogo.query.filter(or_(func.lower(ProdutoCatalogo.nome_produto).contains(func.lower(search_term)), func.lower(ProdutoCatalogo.plu).contains(func.lower(search_term)), ProdutoCatalogo.barcode_1.contains(search_term), ProdutoCatalogo.barcode_2.contains(search_term), ProdutoCatalogo.barcode_3.contains(search_term))).limit(10).all()
    results = [{'id': item.id, 'nome': item.nome_produto, 'plu': item.plu, 'barcode': item.barcode_1 or item.barcode_2 or item.barcode_3} for item in query]
    return jsonify(results)

# --- ROTAS DE RELATÓRIOS (PDFs) ---
@routes.route('/encarregado/relatorio/pdf')
@login_required
def gerar_relatorio_encarregado_pdf():
    if current_user.role != 'encarregado_setor': return redirect(url_for('routes.index'))
    data_inicio_str, data_fim_str = request.args.get('data_inicio'), request.args.get('data_fim')
    if not data_inicio_str or not data_fim_str:
        flash('Datas são obrigatórias.', 'danger'); return redirect(url_for('routes.relatorio_encarregado'))
    
    start_datetime = datetime.combine(datetime.strptime(data_inicio_str, '%Y-%m-%d').date(), time.min)
    end_datetime = datetime.combine(datetime.strptime(data_fim_str, '%Y-%m-%d').date(), time.max)
    
    produtos_db = Produto.query.join(Usuario).filter(Produto.loja_id == current_user.loja_id, Produto.setor_id == current_user.setor_id, Produto.data_cadastro.between(start_datetime, end_datetime)).order_by(Produto.data_cadastro).all()
    
    # ATUALIZADO: Incluindo Qtd e PLU
    lista_simples = [{
        'criado_por': p.criado_por.nome_display if p.criado_por else 'Excluído',
        'data_cadastro': p.data_cadastro.strftime('%d/%m/%Y'),
        'nome_produto': p.nome_produto,
        'plu': p.plu,                  # NOVO
        'quantidade': p.quantidade,    # NOVO
        'validade': p.validade.strftime('%d/%m/%Y'),
        'status': p.status
    } for p in produtos_db]
    
    buffer = io.BytesIO()
    draw_pdf_report(buffer, f"Relatório do Setor: {current_user.setor.nome}", f"Produtos cadastrados de {data_inicio_str} a {data_fim_str}", lista_simples)
    buffer.seek(0)
    return Response(buffer, mimetype='application/pdf', headers={'Content-Disposition': 'inline;filename=relatorio_setor.pdf'})

@routes.route('/gerente/relatorio/pdf')
@login_required
def gerar_relatorio_gerente_pdf():
    if current_user.role != 'gerente': return redirect(url_for('routes.index'))
    data_inicio_str, data_fim_str = request.args.get('data_inicio'), request.args.get('data_fim')
    if not data_inicio_str or not data_fim_str:
        flash('Datas são obrigatórias.', 'danger'); return redirect(url_for('routes.relatorio_gerente'))
    
    start_datetime = datetime.combine(datetime.strptime(data_inicio_str, '%Y-%m-%d').date(), time.min)
    end_datetime = datetime.combine(datetime.strptime(data_fim_str, '%Y-%m-%d').date(), time.max)
    
    produtos_db = Produto.query.join(Usuario).filter(Produto.loja_id == current_user.loja_id, Produto.data_cadastro.between(start_datetime, end_datetime)).order_by(Produto.setor_id, Produto.data_cadastro).all()
    
    # ATUALIZADO: Incluindo Qtd e PLU
    lista_simples = [{
        'criado_por': p.criado_por.nome_display if p.criado_por else 'Excluído',
        'data_cadastro': p.data_cadastro.strftime('%d/%m/%Y'),
        'nome_produto': p.nome_produto,
        'plu': p.plu,                  # NOVO
        'quantidade': p.quantidade,    # NOVO
        'validade': p.validade.strftime('%d/%m/%Y'),
        'status': p.status
    } for p in produtos_db]
    
    buffer = io.BytesIO()
    draw_pdf_report(buffer, f"Relatório da Loja: {current_user.loja.nome}", f"Produtos cadastrados de {data_inicio_str} a {data_fim_str}", lista_simples)
    buffer.seek(0)
    return Response(buffer, mimetype='application/pdf', headers={'Content-Disposition': 'inline;filename=relatorio_loja.pdf'})

@routes.route('/relatorio/pdf')
@login_required
def gerar_relatorio_pdf():
    if current_user.role not in ['gerente_geral', 'gerente_trocas']: return redirect(url_for('routes.index'))
    data_inicio_str, data_fim_str = request.args.get('data_inicio'), request.args.get('data_fim')
    loja_id = request.args.get('loja_id'); search_term = request.args.get('search_term')
    
    query = Produto.query
    subtitulo = ""; is_geral = current_user.role == 'gerente_geral'; titulo = "Relatório Geral de Produtos"
    
    if search_term:
        query = query.join(ProdutoCatalogo, or_(ProdutoCatalogo.barcode_1 == Produto.plu, ProdutoCatalogo.barcode_2 == Produto.plu, ProdutoCatalogo.barcode_3 == Produto.plu), isouter=True).filter(or_(Produto.nome_produto.ilike(f'%{search_term}%'), Produto.plu.ilike(f'%{search_term}%'), ProdutoCatalogo.barcode_1 == search_term, ProdutoCatalogo.barcode_2 == search_term, ProdutoCatalogo.barcode_3 == search_term))
        subtitulo = f"Resultados da busca por '{search_term}'"
    elif data_inicio_str and data_fim_str:
        start_datetime = datetime.combine(datetime.strptime(data_inicio_str, '%Y-%m-%d').date(), time.min)
        end_datetime = datetime.combine(datetime.strptime(data_fim_str, '%Y-%m-%d').date(), time.max)
        query = query.filter(Produto.data_cadastro.between(start_datetime, end_datetime))
        subtitulo = f"Produtos cadastrados de {data_inicio_str} a {data_fim_str}"
    else:
        flash('É necessário preencher um intervalo de datas ou um termo de busca.', 'danger'); return redirect(request.referrer)
    
    if loja_id and loja_id != 'todas':
        query = query.filter(Produto.loja_id == int(loja_id)); loja_obj = Loja.query.get(int(loja_id)); titulo = f"Relatório da Loja: {loja_obj.nome}"
    
    produtos_db = query.outerjoin(Usuario, Produto.criado_por_id == Usuario.id).join(Loja).order_by(Produto.loja_id, Produto.setor_id, Produto.data_cadastro).all()
    
    # ATUALIZADO: Incluindo Qtd e PLU
    lista_simples = []
    for p in produtos_db:
        criado_por_nome = p.criado_por.nome_display if p.criado_por else 'Usuário Excluído'
        item = {
            'criado_por': criado_por_nome,
            'data_cadastro': p.data_cadastro.strftime('%d/%m/%Y'),
            'nome_produto': p.nome_produto,
            'plu': p.plu,               # NOVO
            'quantidade': p.quantidade, # NOVO
            'validade': p.validade.strftime('%d/%m/%Y'),
            'status': p.status
        }
        if is_geral: item['loja'] = p.loja.nome
        lista_simples.append(item)
        
    buffer = io.BytesIO()
    draw_pdf_report(buffer, titulo, subtitulo, lista_simples, is_geral=is_geral)
    buffer.seek(0)
    return Response(buffer, mimetype='application/pdf', headers={'Content-Disposition': 'inline;filename=relatorio.pdf'})