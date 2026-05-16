# app/main/routes.py
from flask import Blueprint, render_template, url_for, redirect
from flask_login import login_required, current_user
from app import db

main = Blueprint('main', __name__)

@main.route('/')
def index():
    # Se já estiver logado, redireciona para a rota oficial do menu
    if current_user.is_authenticated:
        return redirect(url_for('main.menu')) # <--- MELHORIA DE UX
    
    # Aqui seria sua Landing Page (Página de vendas do SaaS)
    # Por enquanto usamos o base.html ou login
    return redirect(url_for('auth.login')) 

@main.route('/menu')
@login_required
def menu():
    tools = [
        {
            'id': 'dashboard',
            'title': 'Dashboard & Analytics',
            'description': 'Visão geral de vendas, lucros e métricas.',
            'route': url_for('main.dashboard'),
            'color': 'primary'
        },
        {
            'id': 'products',
            'title': 'Meus Produtos',
            'description': 'Cadastre, edite e gerencie seu inventário.',
            'route': url_for('produtos.lista_produtos'), 
            'color': 'info'
        },
        {
            'id': 'pricing',
            'title': 'Calculadora de Preços',
            'description': 'Simule margens de lucro e taxas.',
            'route': url_for('pricing.calculator'), # Aponta para o módulo novo
            'color': 'success'
        },
        {
            'id': 'settings',
            'title': 'Configurações',
            'description': 'Dados da conta e segurança.',
            # O url_for(...) gera o link "/settings" correto
            'route': url_for('settings.index'),
            'color': 'secondary'
        }
    ]
    return render_template('menu.html', tools=tools)

@main.route('/dashboard')
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