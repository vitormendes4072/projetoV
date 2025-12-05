from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from flask_mail import Message
from itsdangerous import URLSafeTimedSerializer
# Importações locais limpas e unificadas
from . import db, mail, limiter
from .models import User
from .forms import RegistrationForm, LoginForm, RequestResetForm, ResetPasswordForm, CalculatorForm
import time

main = Blueprint('main', __name__)

# --- FUNÇÕES AUXILIARES (E-MAIL) ---

def send_reset_email(user):
    s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    # CORREÇÃO: Usar um salt específico para senha
    token = s.dumps(user.email, salt='password-reset') 
    
    msg = Message('Redefinição de Senha - Marketplace Manager',
                  sender='noreply@demo.com',
                  recipients=[user.email])
    
    link = url_for('main.reset_token', token=token, _external=True)
    
    msg.body = f'''Para redefinir sua senha, visite o seguinte link:
{link}

Se você não fez essa solicitação, ignore este email.
'''
    try:
        mail.send(msg)
    except Exception as e:
        print(f"\nERRO AO CONECTAR NO GMAIL: {e}")
        print(f"LINK DE REDEFINIÇÃO (Simulação): {link}\n")

def send_confirmation_email(user):
    s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    # CORREÇÃO: Usar um salt específico para confirmação
    token = s.dumps(user.email, salt='email-confirm') 
    
    msg = Message('Confirme sua Conta - Marketplace Manager',
                  sender='noreply@demo.com',
                  recipients=[user.email])
    
    link = url_for('main.confirm_email', token=token, _external=True)
    
    msg.body = f'''Olá, {user.name}!
Para ativar sua conta, clique no link abaixo:
{link}

Se você não se cadastrou, ignore este e-mail.
'''
    try:
        mail.send(msg)
    except Exception as e:
        print(f"\nERRO EMAIL CONFIRMAÇÃO: {e}")
        print(f"LINK (Simulação): {link}\n")

# --- ROTAS PRINCIPAIS ---

@main.route('/')
def index():
    return render_template('base.html')

@main.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
        
    form = RegistrationForm()
    if form.validate_on_submit():
        existing_user = User.query.filter_by(email=form.email.data).first()
        if existing_user:
            flash('Este email já está cadastrado.', 'danger')
            return redirect(url_for('main.register'))
        
        # Cria usuário (confirmed=False por padrão no Model)
        user = User(email=form.email.data, name=form.name.data)
        user.set_password(form.password.data)
        
        db.session.add(user)
        db.session.commit()
        
        send_confirmation_email(user)

        flash('Conta criada com sucesso! Um link de confirmação foi enviado para seu e-mail.', 'info')
        return redirect(url_for('main.login'))
        
    return render_template('register.html', form=form)

@main.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute", methods=['POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.menu'))
        
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        
        if user and user.check_password(form.password.data):
            # Verifica se confirmou o email
            if not user.confirmed:
                flash('Por favor, confirme seu e-mail antes de fazer login.', 'warning')
                return render_template('login.html', form=form)
            
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('main.menu'))
        else:
            flash('Login inválido. Verifique email e senha.', 'danger')
            
    return render_template('login.html', form=form)

@main.route('/menu')
@login_required
def menu():
    # Lista de ferramentas
    tools = [
        {
            'id': 'dashboard',
            'title': 'Dashboard & Analytics',
            'description': 'Visão geral de vendas, lucros e métricas.',
            'route': url_for('main.dashboard'),
            'color': 'primary' # Azul
        },
        {
            'id': 'products',
            'title': 'Meus Produtos',
            'description': 'Cadastre, edite e gerencie seu inventário.',
            'route': '#', 
            'color': 'info' # Azul claro
        },
        {
            'id': 'pricing',
            'title': 'Calculadora de Preços',
            'description': 'Simule margens de lucro e taxas.',
            'route': url_for('main.calculator'),
            'color': 'success' # Verde
        },
        {
            'id': 'settings',
            'title': 'Configurações',
            'description': 'Dados da conta e segurança.',
            'route': '#',
            'color': 'secondary' # Cinza
        }
    ]
    
    return render_template('menu.html', tools=tools)

# Em routes.py

@main.route('/dashboard')
@login_required
def dashboard():
    # Dados Mockados para quando você criar o dashboard.html
    stats = {
        'total_vendas': 'R$ 12.450,00',
        'pedidos_pendentes': 15,
        'produtos_ativos': 42,
        'lucro_mensal': 'R$ 3.200,00'
    }
    

    return "<h1>Dashboard em construção</h1> <a href='/menu'>Voltar</a>"
    
    # Se já criou o dashboard.html (do passo anterior), use este:
    #return render_template('dashboard.html', stats=stats, pedidos=[])

@main.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Você saiu do sistema.', 'info')
    return redirect(url_for('main.login'))

# --- ROTAS DE RECUPERAÇÃO DE SENHA ---

@main.route("/reset_password", methods=['GET', 'POST'])
def reset_request():
    if current_user.is_authenticated:
        return redirect(url_for('main.menu'))
    
    form = RequestResetForm()
    
    if form.validate_on_submit():
        # --- INÍCIO DO CRONÔMETRO DE SEGURANÇA ---
        start_time = time.time()
        
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            send_reset_email(user)
            
        # --- LÓGICA DE TIMING ATTACK ---
        # O envio do Gmail leva em média 1 a 2 segundos.
        # Vamos forçar que TODA requisição leve pelo menos 3 segundos.
        # Assim, se o usuário não existir, o sistema finge que está enviando o e-mail.
        
        elapsed_time = time.time() - start_time
        target_duration = 3.0 # Segundos (Ajuste conforme a lentidão do seu SMTP)
        
        if elapsed_time < target_duration:
            time.sleep(target_duration - elapsed_time)
        # -------------------------------

        flash('Um email foi enviado com instruções para redefinir sua senha.', 'info')
        return redirect(url_for('main.login'))
        
    return render_template('reset_request.html', form=form)

@main.route("/reset_password/<token>", methods=['GET', 'POST'])
def reset_token(token):
    if current_user.is_authenticated:
        return redirect(url_for('main.menu'))
    
    s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    try:
        # CORREÇÃO: Validar com salt de senha
        email = s.loads(token, salt='password-reset', max_age=1800) 
    except:
        flash('O token é inválido ou expirou.', 'danger')
        return redirect(url_for('main.reset_request'))
    
    user = User.query.filter_by(email=email).first()
    
    # Proteção extra: e se o usuário foi deletado nesse meio tempo?
    if not user:
        flash('Usuário não encontrado.', 'danger')
        return redirect(url_for('main.reset_request'))

    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        db.session.commit()
        flash('Sua senha foi atualizada! Você já pode fazer login.', 'success')
        return redirect(url_for('main.login'))
        
    return render_template('reset_token.html', form=form)

# --- ROTA DE CONFIRMAÇÃO DE CONTA ---

@main.route("/confirm/<token>")
def confirm_email(token):
    if current_user.is_authenticated:
        return redirect(url_for('main.menu'))
    
    s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    try:
        # CORREÇÃO: Validar com salt de confirmação
        email = s.loads(token, salt='email-confirm', max_age=3600) 
    except:
        flash('O link de confirmação é inválido ou expirou.', 'danger')
        return redirect(url_for('main.login'))
    
    user = User.query.filter_by(email=email).first()
    
    # Proteção: Verifica se usuário existe antes de tentar alterar o banco
    if not user:
        flash('Usuário inválido ou não encontrado.', 'danger')
        return redirect(url_for('main.login'))
    
    if user.confirmed:
        flash('Sua conta já foi confirmada anteriormente. Faça login.', 'info')
    else:
        user.confirmed = True
        db.session.commit()
        flash('Sua conta foi confirmada! Você já pode fazer login.', 'success')
        
    return redirect(url_for('main.login'))

@main.route('/calculator', methods=['GET', 'POST'])
@login_required
def calculator():
    form = CalculatorForm()
    results = None
    
    if form.validate_on_submit():
        # 1. Captura os dados do formulário
        price = form.price.data
        cost = form.cost.data
        fba_fee = form.fba_fee.data
        referral_pct = form.referral_fee.data
        tax_pct = form.tax_rate.data
        marketing = form.marketing.data or 0
        
        # 2. Cálculos
        # Comissão (Ex: 15% do preço de venda)
        referral_cost = price * (referral_pct / 100)
        
        # Imposto (Ex: 4% do preço de venda)
        tax_cost = price * (tax_pct / 100)
        
        # Custos Totais da Amazon + Imposto + Custo Mercadoria
        total_fees = referral_cost + fba_fee + tax_cost + marketing
        total_cost = cost + total_fees
        
        # Lucro Líquido
        net_profit = price - total_cost
        
        # Margem de Lucro (%) -> (Lucro / Preço Venda) * 100
        margin = (net_profit / price) * 100 if price > 0 else 0
        
        # ROI (%) -> (Lucro / Custo Investido) * 100
        roi = (net_profit / cost) * 100 if cost > 0 else 0
        
        # Empacota os resultados para mandar pro HTML
        results = {
            'revenue': price,
            'total_cost': total_cost,
            'net_profit': net_profit,
            'margin': margin,
            'roi': roi,
            'breakdown': {
                'referral': referral_cost,
                'fba': fba_fee,
                'tax': tax_cost,
                'marketing': marketing,
                'product_cost': cost
            }
        }
        
    return render_template('calculator.html', form=form, results=results)