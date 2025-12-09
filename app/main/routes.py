# app/main/routes.py
from flask import Blueprint, render_template, url_for, redirect
from flask_login import login_required, current_user
# REMOVIDO: from app.forms import CalculatorForm (Não é mais usado aqui)

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
            'route': '#', 
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
            'route': '#',
            'color': 'secondary'
        }
    ]
    return render_template('menu.html', tools=tools)

@main.route('/dashboard')
@login_required
def dashboard():
    # MELHORIA: Usa um template para manter a barra de navegação
    # Crie um arquivo simples dashboard.html ou use o base com uma mensagem
    return render_template('base.html', content="<h1>Dashboard em Construção 🚧</h1>") 
    # Obs: Para isso funcionar bonito, o base.html precisaria de um ajuste, 
    # mas por enquanto evita a tela branca da morte.