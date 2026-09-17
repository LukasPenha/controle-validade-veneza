from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, Response
from flask_login import login_required, current_user
from .models import db, Produto, Usuario, Loja, Setor, agora_brasil, BRASIL, ROLES
from sqlalchemy.exc import IntegrityError
from .notifications import add_event, sync_expiry_notifications
from datetime import datetime, date, time, timedelta
from sqlalchemy import cast, Date, or_, func
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch

routes = Blueprint('routes', __name__)


def user_form(user=None):
    from .preferences import valid_email
    username = valid_email(request.form.get('username', ''))
    role = request.form.get('role')
    password = request.form.get('password', '')
    if role not in ROLES:
        raise ValueError('Selecione um cargo válido.')
    if (not user or password) and (len(password) < 10 or len(password.encode()) > 72):
        raise ValueError('A senha deve ter pelo menos 10 caracteres e no máximo 72 bytes.')
    duplicate = Usuario.query.filter(func.lower(Usuario.username) == username.lower()).first()
    if duplicate and (not user or duplicate.id != user.id):
        raise ValueError('Este e-mail já está em uso.')
    store = sector = None
    if role not in ('gerente_geral', 'gerente_trocas'):
        store = request.form.get('loja_id', type=int)
        if not store or not db.session.get(Loja, store):
            raise ValueError('Selecione uma loja válida para este cargo.')
    if role == 'encarregado_setor':
        sector = request.form.get('setor_id', type=int)
        if not sector or not db.session.get(Setor, sector):
            raise ValueError('Selecione um setor válido.')
    if user and user.id == current_user.id and role != 'gerente_geral':
        raise ValueError('Você não pode remover seu próprio acesso de gerente geral.')
    user = user or Usuario()
    user.username, user.role, user.loja_id, user.setor_id = username, role, store, sector
    if password:
        user.set_password(password)
    return user

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
        headers = ["Loja", "Descrição (Produto)", "Código", "Qtd", "Validade", "Quem Cadastrou"]
        # Posições X (ajustadas para paisagem ou letra apertada)
        col_positions = [inch, inch + 60, inch + 180, inch + 250, inch + 280, inch + 335]
    else:
        # Layout Local: Produto | PLU | Qtd | Validade | Status | Quem Cadastrou
        headers = ["Descrição (Produto)", "Código", "Qtd", "Validade", "Status", "Quem Cadastrou"]
        col_positions = [inch, inch + 140, inch + 210, inch + 240, inch + 295, inch + 365]
    
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
                p.drawString(col_positions[2], y, str(produto.get('barcode', '')))
                p.drawString(col_positions[3], y, str(produto.get('quantidade', '')))
                p.drawString(col_positions[4], y, produto.get('validade', ''))
                p.drawString(col_positions[5], y, produto.get('criado_por', '')[:20])
            else:
                p.drawString(col_positions[0], y, produto.get('nome_produto', '')[:35]) # Trunca nome longo
                p.drawString(col_positions[1], y, str(produto.get('barcode', '')))
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
        'auxiliar_gestao': 'inventory.upcoming'
    }
    dashboard_route = role_dashboard_map.get(current_user.role)
    if dashboard_route: return redirect(url_for(dashboard_route))
    flash('Seu cargo ainda não possui um dashboard definido.', 'info')
    return redirect(url_for('auth.login'))



# --- ROTAS DO GERENTE GERAL ---

@routes.route('/gerente-geral/dashboard')
@login_required
def dashboard_gerente_geral():
    if current_user.role != 'gerente_geral': 
        return redirect(url_for('routes.index'))
    from .analytics import dashboard_data
    return render_template('geral/dashboard.html', **dashboard_data())


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
    if loja_para_excluir.usuarios or loja_para_excluir.produtos:
        flash(f'Não é possível excluir a loja "{loja_para_excluir.nome}", pois ela possui usuários ou produtos vinculados.', 'danger')
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
        try:
            db.session.add(user_form())
            db.session.commit()
            flash('Usuário criado com sucesso!', 'success')
        except (ValueError, IntegrityError) as error:
            db.session.rollback()
            flash(str(error) if isinstance(error, ValueError) else 'Este e-mail já está em uso.', 'danger')
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
    try:
        user_form(usuario)
        db.session.commit()
        flash('Usuário atualizado com sucesso!', 'success')
    except (ValueError, IntegrityError) as error:
        db.session.rollback()
        flash(str(error) if isinstance(error, ValueError) else 'Este e-mail já está em uso.', 'danger')
    return redirect(url_for('routes.gerenciar_usuarios_geral'))

@routes.route('/gerente-geral/usuario/excluir/<int:usuario_id>', methods=['POST'])
@login_required
def excluir_usuario(usuario_id):
    if current_user.role != 'gerente_geral': return redirect(url_for('routes.index'))
    if usuario_id == current_user.id:
        flash('Você não pode excluir seu próprio acesso.', 'warning')
        return redirect(url_for('routes.gerenciar_usuarios_geral'))
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
    produtos = Produto.query.filter(Produto.quantidade > 0, Produto.arquivado.is_(False), Produto.loja_id == current_user.loja_id, Produto.status == 'Para Rebaixa', Produto.validade >= agora_brasil().date()).order_by(Produto.validade.asc()).paginate(page=page, per_page=20)
    return render_template('gerente/produtos_para_rebaixa.html', produtos_para_rebaixa=produtos, now=agora_brasil())

@routes.route('/gerente/em-rebaixa')
@login_required
def produtos_em_rebaixa():
    if current_user.role != 'gerente': return redirect(url_for('routes.index'))
    page = request.args.get('page', 1, type=int)
    produtos = Produto.query.filter(Produto.quantidade > 0, Produto.arquivado.is_(False), Produto.loja_id == current_user.loja_id, Produto.status == 'Em Rebaixa', Produto.validade >= agora_brasil().date()).order_by(Produto.validade.asc()).paginate(page=page, per_page=20)
    return render_template('gerente/produtos_em_rebaixa.html', produtos_em_rebaixa=produtos, now=agora_brasil())

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
    produtos = Produto.query.filter(Produto.quantidade > 0, Produto.arquivado.is_(False), Produto.loja_id == current_user.loja_id, Produto.setor_id == current_user.setor_id, Produto.validade >= agora_brasil().date()).order_by(Produto.validade.asc()).paginate(page=page, per_page=20)
    return render_template('encarregado/listar_produtos.html', produtos=produtos, now=agora_brasil())

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
    data_limite = agora_brasil().date() - timedelta(days=30)
    produtos_vencidos = Produto.query.filter(Produto.quantidade > 0, Produto.arquivado.is_(False), Produto.loja_id == current_user.loja_id, Produto.setor_id == current_user.setor_id, Produto.validade < agora_brasil().date(), Produto.validade >= data_limite).order_by(Produto.validade.asc()).paginate(page=page, per_page=20)
    return render_template('encarregado/produtos_vencidos.html', produtos=produtos_vencidos, today=agora_brasil().date())

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
    if current_user.role == 'gerente_trocas':
        return redirect(url_for('inventory.upcoming', situacao='vencidos'))
    if current_user.role not in ['gerente', 'gerente_geral', 'gerente_trocas']: return redirect(url_for('routes.index'))
    page = request.args.get('page', 1, type=int)
    data_limite = agora_brasil().date() - timedelta(days=30)
    query = Produto.query.filter(Produto.quantidade > 0, Produto.arquivado.is_(False), Produto.validade < agora_brasil().date(), Produto.validade >= data_limite)
    if current_user.role == 'gerente':
        query = query.filter(Produto.loja_id == current_user.loja_id)
        produtos_vencidos = query.order_by(Produto.validade.asc()).paginate(page=page, per_page=20)
        return render_template('gerente/produtos_vencidos.html', produtos=produtos_vencidos, today=agora_brasil().date())
    produtos_vencidos = query.order_by(Produto.loja_id, Produto.validade.asc()).paginate(page=page, per_page=20)
    return render_template('geral/produtos_vencidos.html', produtos=produtos_vencidos, today=agora_brasil().date())

@routes.route('/produtos/bulk-action', methods=['POST'])
@login_required
def bulk_action():
    flash('Abra o produto para encerrar o acompanhamento e informar o motivo.', 'info')
    return redirect(url_for('inventory.index'))

@routes.route('/produtos/<int:produto_id>/editar', methods=['POST'])
@login_required
def editar_produto(produto_id):
    if current_user.role != 'encarregado_setor': return redirect(url_for('routes.index'))
    produto = Produto.query.filter_by(id=produto_id).with_for_update().first_or_404()
    if produto.loja_id != current_user.loja_id or produto.setor_id != current_user.setor_id:
        flash('Você só pode editar produtos do seu setor.', 'danger')
        return redirect(url_for('routes.listar_produtos_encarregado'))
    try:
        quantity = int(request.form.get('quantidade', ''))
        validity = date.fromisoformat(request.form.get('validade', ''))
        reason = request.form.get('motivo_rebaixa', '').strip()
        if not 1 <= quantity <= 2147483647 or len(reason) > 255 or produto.arquivado:
            raise ValueError()
    except (ValueError, TypeError):
        flash('Confira a quantidade positiva, validade e motivo.', 'danger')
        return redirect(url_for('routes.listar_produtos_encarregado'))
    produto.quantidade, produto.validade, produto.motivo_rebaixa = quantity, validity, reason
    db.session.commit()
    flash('Produto atualizado com sucesso!', 'success')
    sync_expiry_notifications(user=current_user)
    return redirect(url_for('routes.listar_produtos_encarregado'))

@routes.route('/produtos/<int:produto_id>/status', methods=['POST'])
@login_required
def alterar_status(produto_id):
    if current_user.role != 'gerente': return redirect(url_for('routes.index'))
    produto = Produto.query.filter_by(id=produto_id,arquivado=False).with_for_update().first_or_404()
    if produto.loja_id != current_user.loja_id: return redirect(url_for('routes.index'))
    novo_status = request.form.get('status')
    if novo_status == produto.status:
        return redirect(url_for('routes.index'))
    if novo_status in ['Para Rebaixa', 'Em Rebaixa']:
        produto.status = novo_status
        mensagem = f"Status de '{produto.nome_produto}' alterado para '{novo_status}' por {current_user.nome_display}."
        add_event(produto, f'status:{produto.id}:{novo_status}:{agora_brasil().isoformat()}', 'status', 'info', mensagem)
        db.session.commit()
        flash(f'Status do produto {produto.nome_produto} alterado.', 'success')
    else: flash('Status inválido.', 'danger')
    return redirect(url_for('routes.index'))

@routes.route('/produtos/<int:produto_id>/excluir', methods=['POST'])
@login_required
def excluir_produto(produto_id):
    if current_user.role not in ['encarregado_setor', 'gerente_geral', 'gerente']: return redirect(url_for('routes.index'))
    produto = Produto.query.get_or_404(produto_id)
    if current_user.role == 'encarregado_setor' and (produto.loja_id != current_user.loja_id or produto.setor_id != current_user.setor_id): return redirect(url_for('routes.index'))
    if current_user.role == 'gerente' and produto.loja_id != current_user.loja_id: return redirect(url_for('routes.index'))
    return redirect(url_for('inventory.detail',item_id=produto.id))

# --- ROTAS PARA DATAS CURTAS ---
@routes.route('/datas-curtas')
@login_required
def datas_curtas():
    if current_user.role not in ['gerente_geral', 'gerente', 'encarregado_setor', 'auxiliar_gestao']:
        flash('Você não tem permissão para acessar esta página.', 'danger')
        return redirect(url_for('routes.index'))
    return render_template('geral/datas_curtas.html')


# --- ROTAS DE RELATÓRIOS (PDFs) ---
@routes.route('/encarregado/relatorio/pdf')
@login_required
def gerar_relatorio_encarregado_pdf():
    if current_user.role != 'encarregado_setor': return redirect(url_for('routes.index'))
    data_inicio_str, data_fim_str = request.args.get('data_inicio'), request.args.get('data_fim')
    if not data_inicio_str or not data_fim_str:
        flash('Datas são obrigatórias.', 'danger'); return redirect(url_for('routes.relatorio_encarregado'))
    
    start_datetime = datetime.combine(datetime.strptime(data_inicio_str, '%Y-%m-%d').date(), time.min, tzinfo=BRASIL)
    end_datetime = datetime.combine(datetime.strptime(data_fim_str, '%Y-%m-%d').date(), time.max, tzinfo=BRASIL)
    
    produtos_db = Produto.query.join(Usuario).filter(Produto.loja_id == current_user.loja_id, Produto.setor_id == current_user.setor_id, Produto.data_cadastro.between(start_datetime, end_datetime)).order_by(Produto.data_cadastro).all()
    
    # ATUALIZADO: Incluindo Qtd e PLU
    lista_simples = [{
        'criado_por': p.criado_por.nome_display if p.criado_por else 'Excluído',
        'data_cadastro': p.data_cadastro.strftime('%d/%m/%Y'),
        'nome_produto': p.nome_produto,
        'barcode': p.barcode,                  # NOVO
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
    
    start_datetime = datetime.combine(datetime.strptime(data_inicio_str, '%Y-%m-%d').date(), time.min, tzinfo=BRASIL)
    end_datetime = datetime.combine(datetime.strptime(data_fim_str, '%Y-%m-%d').date(), time.max, tzinfo=BRASIL)
    
    produtos_db = Produto.query.join(Usuario).filter(Produto.loja_id == current_user.loja_id, Produto.data_cadastro.between(start_datetime, end_datetime)).order_by(Produto.setor_id, Produto.data_cadastro).all()
    
    # ATUALIZADO: Incluindo Qtd e PLU
    lista_simples = [{
        'criado_por': p.criado_por.nome_display if p.criado_por else 'Excluído',
        'data_cadastro': p.data_cadastro.strftime('%d/%m/%Y'),
        'nome_produto': p.nome_produto,
        'barcode': p.barcode,                  # NOVO
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
        query = query.filter(or_(Produto.nome_produto.ilike(f'%{search_term}%'),
                                 Produto.plu.ilike(f'%{search_term}%'), Produto.barcode == search_term))
        subtitulo = f"Resultados da busca por '{search_term}'"
    elif data_inicio_str and data_fim_str:
        start_datetime = datetime.combine(datetime.strptime(data_inicio_str, '%Y-%m-%d').date(), time.min, tzinfo=BRASIL)
        end_datetime = datetime.combine(datetime.strptime(data_fim_str, '%Y-%m-%d').date(), time.max, tzinfo=BRASIL)
        query = query.filter(Produto.data_cadastro.between(start_datetime, end_datetime))
        subtitulo = f"Produtos cadastrados de {data_inicio_str} a {data_fim_str}"
    else:
        flash('É necessário preencher um intervalo de datas ou um termo de busca.', 'danger'); return redirect(url_for('routes.index'))
    
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
            'barcode': p.barcode,               # NOVO
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
