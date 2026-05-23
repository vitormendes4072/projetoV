# app/auth/routes.py
import logging
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, current_user, login_required
from flask_mail import Message
from itsdangerous import URLSafeTimedSerializer
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
        except Exception:
            logger.exception("Falha ao enviar email async")

def send_reset_email(user):
    s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    token = s.dumps(user.email, salt='password-reset')
    msg = Message('Redefinição de Senha - VEntregaz',
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
    msg = Message('Confirme sua Conta - VEntregaz',
                  sender=current_app.config.get('MAIL_DEFAULT_SENDER'),
                  recipients=[user.email])
    link = url_for('auth.confirm_email', token=token, _external=True)
    msg.body = f'''Ative sua conta aqui: {link}'''

    Thread(target=send_async_email, args=(current_app._get_current_object(), msg)).start()


def send_account_exists_email(user):
    """Enviado quando alguém tenta registrar um e-mail já cadastrado.
    Não revela a existência da conta na UI — a resposta HTTP é sempre idêntica.
    """
    reset_link  = url_for('auth.reset_request', _external=True)
    msg = Message('Tentativa de cadastro - VEntregaz',
                  sender=current_app.config.get('MAIL_DEFAULT_SENDER'),
                  recipients=[user.email])
    msg.body = (
        f"Recebemos uma solicitação de cadastro com este e-mail, "
        f"mas ele já possui uma conta no VEntregaz.\n\n"
        f"Se foi você, faça login normalmente. "
        f"Esqueceu a senha? Redefina aqui: {reset_link}\n\n"
        f"Se não foi você, ignore este e-mail."
    )
    Thread(target=send_async_email, args=(current_app._get_current_object(), msg)).start()

# --- ROTAS DE AUTENTICAÇÃO ---

@auth.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    form = RegistrationForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        existing_user = db.session.scalar(db.select(User).filter_by(email=email))
        if existing_user:
            send_account_exists_email(existing_user)
        else:
            user = User(email=email, name=form.name.data)
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()
            send_confirmation_email(user)

        # Mensagem genérica independente de o e-mail já existir ou não.
        flash('Conta criada! Verifique seu e-mail.', 'info')
        return redirect(url_for('auth.login'))
    return render_template('register.html', form=form)

@auth.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute", methods=['POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    form = LoginForm()
    if form.validate_on_submit():
        user = db.session.scalar(db.select(User).filter_by(email=form.email.data.strip().lower()))
        if user and user.check_password(form.password.data):
            if not user.confirmed:
                flash('Confirme seu e-mail antes de logar.', 'warning')
                return render_template('login.html', form=form)

            login_user(user)

            # Captura o argumento 'next'
            next_page = request.args.get('next')

            ### MELHORIA DE SEGURANÇA: Previne Open Redirect ###
            # Se next_page existir MAS tiver um domínio (netloc), ignoramos e vamos pro dashboard
            if not next_page or urlsplit(next_page).netloc != '':
                next_page = url_for('main.dashboard')

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
@limiter.limit("5 per hour", methods=["POST"])
def reset_request():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    form = RequestResetForm()
    if form.validate_on_submit():
        user = db.session.scalar(db.select(User).filter_by(email=form.email.data.strip().lower()))
        if user:
            send_reset_email(user)
        flash('Email enviado.', 'info')
        return redirect(url_for('auth.login'))
    return render_template('reset_request.html', form=form)

@auth.route("/reset_password/<token>", methods=['GET', 'POST'])
def reset_token(token):
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])

    # 1. Valida assinatura + max_age (30 min)
    try:
        email = s.loads(token, salt='password-reset', max_age=1800)
    except Exception:
        flash('Token inválido/expirado.', 'danger')
        return redirect(url_for('auth.reset_request'))

    user = db.session.scalar(db.select(User).filter_by(email=email))
    if not user:
        flash('Usuário não encontrado.', 'danger')
        return redirect(url_for('auth.reset_request'))

    # 2. Rejeita token já utilizado: extrai o timestamp de emissão do token
    # e compara com password_changed_at. Se a senha foi alterada APÓS a emissão,
    # o token é inválido — impede reutilização dentro da janela de 30 min.
    try:
        from datetime import timezone as _tz
        _, token_issued_at = s.make_signer('password-reset').unsign(
            token, return_timestamp=True
        )
        token_issued_at = token_issued_at.replace(tzinfo=_tz.utc)
        if (
            user.password_changed_at is not None
            and token_issued_at < user.password_changed_at.replace(tzinfo=_tz.utc)
        ):
            flash('Este link já foi utilizado. Solicite um novo.', 'danger')
            return redirect(url_for('auth.reset_request'))
    except Exception:
        # Se não conseguir extrair o timestamp (token malformado), nega por segurança
        flash('Token inválido/expirado.', 'danger')
        return redirect(url_for('auth.reset_request'))

    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)  # carimba password_changed_at automaticamente
        db.session.commit()
        flash('Senha atualizada.', 'success')
        return redirect(url_for('auth.login'))
    return render_template('reset_token.html', form=form)

@auth.route("/demo-login")
@limiter.limit("10 per minute")
def demo_login():
    from app.commands import DEMO_EMAIL, _do_seed_demo
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    _do_seed_demo()
    user = db.session.scalar(db.select(User).filter_by(email=DEMO_EMAIL))
    if not user:
        flash("Conta demo não disponível no momento.", "warning")
        return redirect(url_for("auth.login"))
    login_user(user)
    return redirect(url_for("main.dashboard"))


@auth.route("/confirm/<token>")
def confirm_email(token):
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    try:
        email = s.loads(token, salt='email-confirm', max_age=3600)
    except Exception:
        flash('Link inválido/expirado.', 'danger')
        return redirect(url_for('auth.login'))
    user = db.session.scalar(db.select(User).filter_by(email=email))
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
