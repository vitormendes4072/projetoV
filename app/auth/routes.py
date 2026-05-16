# app/auth/routes.py
import logging
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, current_user, login_required
from flask_mail import Message
from itsdangerous import URLSafeTimedSerializer
import time
from threading import Thread
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

# Importações locais
from app import db, mail, limiter
from app.models import User
from .forms import RegistrationForm, LoginForm, RequestResetForm, ResetPasswordForm

auth = Blueprint('auth', __name__)

# --- FUNÇÕES AUXILIARES DE E-MAIL (ASSÍNCRONAS) ---

### MELHORIA DE PERFORMANCE: Função que roda em background
def send_async_email(app, msg):
    # O Flask precisa do contexto da aplicação para acessar as configs de email dentro da Thread
    with app.app_context():
        try:
            mail.send(msg)
        except Exception as e:
            logger.exception("Falha ao enviar email async")

def send_reset_email(user):
    s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    token = s.dumps(user.email, salt='password-reset') 
    msg = Message('Redefinição de Senha - Marketplace Manager',
                  sender=current_app.config.get('MAIL_DEFAULT_SENDER'),
                  recipients=[user.email])
    link = url_for('auth.reset_token', token=token, _external=True)
    msg.body = f'''Para redefinir sua senha, visite: {link}'''
    
    ### MELHORIA: Dispara e esquece (não trava o usuário)
    # Passamos o 'current_app._get_current_object()' para garantir que a Thread tenha acesso às configs
    Thread(target=send_async_email, args=(current_app._get_current_object(), msg)).start()

def send_confirmation_email(user):
    s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    token = s.dumps(user.email, salt='email-confirm') 
    msg = Message('Confirme sua Conta - Marketplace Manager',
                  sender=current_app.config.get('MAIL_DEFAULT_SENDER'),
                  recipients=[user.email])
    link = url_for('auth.confirm_email', token=token, _external=True)
    msg.body = f'''Ative sua conta aqui: {link}'''
    
    ### MELHORIA: Dispara e esquece
    Thread(target=send_async_email, args=(current_app._get_current_object(), msg)).start()

# --- ROTAS DE AUTENTICAÇÃO ---

@auth.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.menu'))
    form = RegistrationForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash('Este email já está cadastrado.', 'danger')
            return redirect(url_for('auth.register'))

        user = User(email=email, name=form.name.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        
        # O envio agora é instantâneo para o usuário
        send_confirmation_email(user)
        
        flash('Conta criada! Verifique seu e-mail.', 'info')
        return redirect(url_for('auth.login'))
    return render_template('register.html', form=form)

@auth.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute", methods=['POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.menu'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.strip().lower()).first()
        if user and user.check_password(form.password.data):
            if not user.confirmed:
                flash('Confirme seu e-mail antes de logar.', 'warning')
                return render_template('login.html', form=form)
            
            login_user(user)
            
            # Captura o argumento 'next'
            next_page = request.args.get('next')
            
            ### MELHORIA DE SEGURANÇA: Previne Open Redirect ###
            # Se next_page existir MAS tiver um domínio (netloc), ignoramos e vamos pro menu
            if not next_page or urlsplit(next_page).netloc != '':
                next_page = url_for('main.menu')
            
            return redirect(next_page)
        else:
            flash('Login inválido.', 'danger')
    return render_template('login.html', form=form)

@auth.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Você saiu do sistema.', 'info')
    return redirect(url_for('auth.login'))

@auth.route("/reset_password", methods=['GET', 'POST'])
def reset_request():
    if current_user.is_authenticated:
        return redirect(url_for('main.menu'))
    form = RequestResetForm()
    if form.validate_on_submit():
        start_time = time.time()
        user = User.query.filter_by(email=form.email.data.strip().lower()).first()
        if user:
            send_reset_email(user)
        
        # Timing attack mitigation (mantido)
        elapsed_time = time.time() - start_time
        if elapsed_time < 3.0:
            time.sleep(3.0 - elapsed_time)
            
        flash('Email enviado.', 'info')
        return redirect(url_for('auth.login'))
    return render_template('reset_request.html', form=form)

@auth.route("/reset_password/<token>", methods=['GET', 'POST'])
def reset_token(token):
    if current_user.is_authenticated:
        return redirect(url_for('main.menu'))
    s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    try:
        email = s.loads(token, salt='password-reset', max_age=1800)
    except:
        flash('Token inválido/expirado.', 'danger')
        return redirect(url_for('auth.reset_request'))
    user = User.query.filter_by(email=email).first()
    if not user:
        flash('Usuário não encontrado.', 'danger')
        return redirect(url_for('auth.reset_request'))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        db.session.commit()
        flash('Senha atualizada.', 'success')
        return redirect(url_for('auth.login'))
    return render_template('reset_token.html', form=form)

@auth.route("/confirm/<token>")
def confirm_email(token):
    if current_user.is_authenticated:
        return redirect(url_for('main.menu'))
    s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    try:
        email = s.loads(token, salt='email-confirm', max_age=3600)
    except:
        flash('Link inválido/expirado.', 'danger')
        return redirect(url_for('auth.login'))
    user = User.query.filter_by(email=email).first()
    if not user:
        flash('Usuário inválido.', 'danger')
        return redirect(url_for('auth.login'))
    if user.confirmed:
        flash('Já confirmado.', 'info')
    else:
        user.confirmed = True
        db.session.commit()
        flash('Conta confirmada!', 'success')
    return redirect(url_for('auth.login'))