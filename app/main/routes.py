# app/main/routes.py
from flask import Blueprint, render_template, url_for, redirect, request
from flask_login import login_required, current_user
from werkzeug.routing import BuildError

main = Blueprint("main", __name__)


def safe_url_for(endpoint: str, fallback: str = "#") -> str:
    """
    Gera url_for(endpoint) sem quebrar a página caso o endpoint não exista.
    """
    try:
        return url_for(endpoint)
    except BuildError:
        return fallback


@main.route("/")
def index():
    # Se já estiver logado, redireciona para a rota oficial do menu
    if current_user.is_authenticated:
        return redirect(url_for("main.menu"))

    # Landing Page futura (SaaS). Por enquanto, manda para login.
    return redirect(url_for("auth.login"))


@main.route("/menu")
@login_required
def menu():
    # Rotas (calculadas 1x para não repetir safe_url_for várias vezes)
    vendas_url = safe_url_for("vendas.index")
    estoque_url = safe_url_for("estoque.index")
    relatorios_url = safe_url_for("relatorios.index")

    # Para calculator/settings você confirmou que existe URL direta:
    calculator_url = safe_url_for("main.calculator", fallback="/calculator")
    settings_url = safe_url_for("main.settings", fallback="/settings")

    tools = [
        # ✅ EXISTE - Dashboard
        {
            "id": "dashboard",
            "title": "Dashboard",
            "description": "Visão geral de vendas, lucro, margem e alertas do negócio.",
            "route": safe_url_for("main.dashboard"),
            "color": "primary",
            "enabled": True,
        },

        # ✅ EXISTE - Financeiro
        {
            "id": "finance_alertas",
            "title": "Alertas Financeiros",
            "description": "Acompanhe alertas de custo, margem, estoque e inconsistências.",
            "route": safe_url_for("financeiro.alertas"),
            "color": "warning",
            "enabled": True,
        },
        {
            "id": "finance_custos_fixos",
            "title": "Custos Fixos",
            "description": "Cadastre e controle custos fixos: vencimentos, categorias e totais.",
            "route": safe_url_for("financeiro.custos_fixos"),
            "color": "success",
            "enabled": True,
        },

        # ✅ EXISTE - Produtos / Cadastro
        {
            "id": "products",
            "title": "Produtos (SKUs)",
            "description": "Cadastre produtos, SKUs e custos base.",
            "route": safe_url_for("produtos.criar_produto"),
            "color": "primary",
            "enabled": True,
        },

        # ✅ EXISTE - Precificação (Simulador FBA)
        # Se endpoint não existir, cai em /calculator, então segue enabled
        {
            "id": "pricing",
            "title": "Precificação",
            "description": "Simulador FBA: calcule e salve cenários de lucro.",
            "route": safe_url_for("pricing.calculator", fallback="/calculator"),
            "color": "primary",
            "enabled": calculator_url != "#",
        },

        # ❌ Em breve (se não existir blueprint)
        {
            "id": "sales",
            "title": "Vendas",
            "description": "Consulte pedidos, performance por período e detalhamento por SKU.",
            "route": vendas_url,
            "color": "success",
            "enabled": vendas_url != "#",
            "badge": None if vendas_url != "#" else "Em breve",
        },
        {
            "id": "inventory",
            "title": "Estoque & Reposição",
            "description": "Controle estoque e sugira reposição por lead time e giro.",
            "route": estoque_url,
            "color": "warning",
            "enabled": estoque_url != "#",
            "badge": None if estoque_url != "#" else "Em breve",
        },
        {
            "id": "reports",
            "title": "Relatórios",
            "description": "Gere relatórios (CSV/PDF) e consolide indicadores por SKU e período.",
            "route": relatorios_url,
            "color": "primary",
            "enabled": relatorios_url != "#",
            "badge": None if relatorios_url != "#" else "Em breve",
        },

        # ✅ EXISTE - Configurações
        # Se endpoint não existir, cai em /settings, então segue enabled
        {
            "id": "settings",
            "title": "Configurações",
            "description": "Dados da conta, parâmetros e configuração fiscal.",
            "route": safe_url_for("settings.index", fallback="/settings"),
            "color": "default",
            "enabled": settings_url != "#",
        },

        {
            "id": "amazon_orders",
            "title": "Pedidos Amazon",
            "description": "Listar pedidos importados da Amazon e ver lucro por pedido.",
            "route": "/integrations/amazon/orders",
            "color": "primary",
            "enabled": True,
        },

    ]

    return render_template("menu.html", tools=tools)


_VALID_PERIODS = {"7d", "30d", "90d", "all"}

@main.route("/dashboard")
@login_required
def dashboard():
    from app.services.dashboard import get_dashboard_kpis
    period = request.args.get("period", "30d")
    if period not in _VALID_PERIODS:
        period = "30d"
    kpis = get_dashboard_kpis(current_user.id, period)
    return render_template("dashboard.html", period=period, **kpis)
