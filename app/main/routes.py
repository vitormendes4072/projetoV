# app/main/routes.py
from flask import Blueprint, render_template, url_for, redirect
from flask_login import login_required, current_user
from werkzeug.routing import BuildError
from app import db

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


@main.route("/dashboard")
@login_required
def dashboard():
    from app.models.pricing import PricingHistory
    from app.models.product import Product, ProductHistory

    user_id = current_user.id

    total_products = current_user.products.count()
    total_simulations = PricingHistory.query.filter_by(user_id=user_id).count()
    avg_margin = db.session.query(db.func.avg(PricingHistory.margin))\
                           .filter_by(user_id=user_id).scalar() or 0
    avg_roi = db.session.query(db.func.avg(PricingHistory.roi))\
                        .filter_by(user_id=user_id).scalar() or 0

    recent_simulations = PricingHistory.query.filter_by(user_id=user_id)\
        .order_by(PricingHistory.created_at.desc()).limit(5).all()

    recent_changes = ProductHistory.query.filter_by(user_id=user_id)\
        .order_by(ProductHistory.changed_at.desc()).limit(5).all()

    low_stock = current_user.products\
        .filter(Product.stock_quantity <= 5)\
        .order_by(Product.stock_quantity.asc()).limit(5).all()

    return render_template('dashboard.html',
        total_products=total_products,
        total_simulations=total_simulations,
        avg_margin=avg_margin,
        avg_roi=avg_roi,
        recent_simulations=recent_simulations,
        recent_changes=recent_changes,
        low_stock=low_stock
    )
