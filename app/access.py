"""Menu e autorização de páginas compartilham as mesmas permissões por perfil."""
from flask import abort, request
from flask_login import current_user

NAV = {
    'upcoming': ('inventory.upcoming', 'Validades próximas', 'calendar-range'),
    'products': ('inventory.index', 'Produtos e exposição', 'box-seam'),
    'history': ('inventory.history', 'Histórico', 'clock-history'),
    'dashboard': ('routes.dashboard_gerente_geral', 'Dashboard', 'speedometer2'),
    'stores': ('routes.gerenciar_lojas', 'Gerenciar lojas', 'shop'),
    'users': ('routes.gerenciar_usuarios_geral', 'Gerenciar usuários', 'person-plus'),
    'general_report': ('routes.relatorio_gerente_geral', 'Relatórios', 'file-earmark-bar-graph'),
    'profile': ('profile.settings', 'Meu perfil e alertas', 'sliders2'),
    'short_dates': ('routes.datas_curtas', 'Datas curtas', 'upc-scan'),
    'alerts': ('notifications.center', 'Central de alertas', 'bell'),
    'trade_report': ('routes.dashboard_gerente_trocas', 'Relatórios', 'file-earmark-bar-graph'),
    'expired': ('routes.pagina_produtos_vencidos', 'Vencidos de todas as lojas', 'calendar-x'),
    'markdown_pending': ('routes.produtos_para_rebaixa', 'Para Rebaixa', 'arrow-down-circle'),
    'markdown_active': ('routes.produtos_em_rebaixa', 'Em Rebaixa', 'tag'),
    'manager_report': ('routes.relatorio_gerente', 'Relatórios', 'file-earmark-bar-graph'),
    'store_expired': ('routes.pagina_produtos_vencidos', 'Vencidos (Loja)', 'calendar-x'),
    'sector_products': ('routes.listar_produtos_encarregado', 'Listar Produtos', 'list-task'),
    'sector_report': ('routes.relatorio_encarregado', 'Relatórios', 'file-earmark-bar-graph'),
    'sector_expired': ('routes.vencidos_encarregado', 'Vencidos (Setor)', 'calendar-x'),
}
MENUS = {
    'gerente_geral': ('upcoming','dashboard','stores','users','general_report','profile'),
    'auxiliar_gestao': ('upcoming','short_dates','alerts'),
    'gerente_trocas': ('trade_report','expired','upcoming'),
    'gerente': ('upcoming','products','history','markdown_pending','markdown_active','short_dates','manager_report','store_expired','alerts','profile'),
    'encarregado_setor': ('upcoming','products','history','sector_products','short_dates','sector_report','sector_expired','alerts','profile'),
}
SUPPORT = {
    'gerente_geral': {'routes.editar_loja','routes.excluir_loja','routes.editar_usuario',
                     'routes.excluir_usuario','routes.gerar_relatorio_pdf','profile.verify',
                     'inventory.detail','inventory.photo'},
    'auxiliar_gestao': {'lookup.search','lots.create','notifications.mark_read',
                       'notifications.mark_all_read','notifications.refresh'},
    'gerente_trocas': {'routes.gerar_relatorio_pdf'},
}


def can_access(endpoint):
    if not current_user.is_authenticated:
        return False
    role = current_user.role
    if role not in MENUS:
        return False
    if endpoint == 'static' or endpoint == 'routes.index' or endpoint.startswith('auth.'):
        return True
    if role not in SUPPORT:  # Existing manager/sector checks remain in their routes.
        return True
    return endpoint in SUPPORT[role] or endpoint in {NAV[key][0] for key in MENUS[role]}


def register_access(app):
    @app.before_request
    def authorize_page():
        if request.endpoint and current_user.is_authenticated and not can_access(request.endpoint):
            abort(403)

    @app.context_processor
    def navigation():
        role = current_user.role if current_user.is_authenticated else None
        return {'navigation_items': [NAV[key] for key in MENUS.get(role, ())], 'can_access': can_access}
