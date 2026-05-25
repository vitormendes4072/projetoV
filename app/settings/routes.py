# app/settings/routes.py
import logging
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, g, jsonify
from flask_login import login_required, current_user
from flask_mail import Message
from threading import Thread
from itsdangerous import URLSafeTimedSerializer
from app import db, mail
from .forms import UpdateAccountForm, ChangePasswordForm, BusinessSettingsForm, WebhookForm

logger = logging.getLogger(__name__)

settings_bp = Blueprint('settings', __name__)

# --- FUNÇÕES AUXILIARES ---
def send_async_email(app, msg):
    with app.app_context():
        try:
            mail.send(msg)
        except Exception:
            logger.exception("Falha ao enviar email de confirmação")

def send_update_email(user, new_email):
    s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    token = s.dumps({'new_email': new_email, 'user_id': user.id}, salt='email-update')

    msg = Message('Confirme seu novo E-mail - VEntregaz',
                  sender=current_app.config.get('MAIL_DEFAULT_SENDER'), recipients=[new_email])

    link = url_for('settings.confirm_email_update', token=token, _external=True)

    msg.body = f'''Olá, {user.name}!
Para confirmar a troca de e-mail, clique no link abaixo:
{link}
'''
    Thread(target=send_async_email, args=(current_app._get_current_object(), msg)).start()

# --- ROTAS ---

@settings_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def index():
    account_form = UpdateAccountForm()
    password_form = ChangePasswordForm()
    business_form = BusinessSettingsForm()
    webhook_form = WebhookForm()

    # Conta demo: bloqueia mudanças de perfil e senha
    if request.method == "POST" and g.is_demo and (
        "submit" in request.form or "submit_password" in request.form
    ):
        flash("Conta demo — alterações de perfil e senha não são permitidas.", "warning")
        return redirect(url_for("settings.index"))

    # ==========================================================
    # 1. LÓGICA DO PERFIL (Nome/Email) - MODAL VERMELHO
    # ==========================================================
    if 'submit' in request.form and account_form.validate_on_submit():

        # VERIFICAÇÃO DE SENHA (BACKEND)
        if not current_user.check_password(account_form.current_password.data):
            # TRUQUE DE UX: Adiciona erro ao campo para reabrir o modal
            account_form.current_password.errors.append('Senha incorreta. Tente novamente.')

        else:
            # Se a senha estiver certa, prossegue...
            has_changes = False

            if account_form.name.data != current_user.name:
                current_user.name = account_form.name.data
                db.session.commit()
                flash('Nome atualizado!', 'success')
                has_changes = True

            if account_form.email.data.strip().lower() != current_user.email:
                send_update_email(current_user, account_form.email.data.strip().lower())
                flash(f'Link de confirmação enviado para {account_form.email.data}', 'info')
                has_changes = True

            if has_changes:
                return redirect(url_for('settings.index'))

    # ==========================================================
    # 2. LÓGICA DA SENHA (Troca de Senha) - MODAL ESCURO
    # ==========================================================
    if 'submit_password' in request.form and password_form.validate_on_submit():

        # VERIFICAÇÃO DE SENHA ATUAL (BACKEND)
        if not current_user.check_password(password_form.current_password.data):
            password_form.current_password.errors.append('A senha atual informada está incorreta.')

        else:
            current_user.set_password(password_form.new_password.data)
            db.session.commit()
            flash('Sua senha foi alterada com sucesso!', 'success')
            return redirect(url_for('settings.index'))

    # ==========================================================
    # 3. LÓGICA: DADOS TRIBUTÁRIOS (Fiscal)
    # ==========================================================
    if 'submit_webhook' in request.form:
        if webhook_form.validate_on_submit():
            current_user.webhook_url = webhook_form.webhook_url.data or None
            db.session.commit()
            flash('Webhook atualizado!', 'success')
            return redirect(url_for('settings.index'))
        else:
            logger.warning("Falha ao salvar webhook: %s", webhook_form.errors)

    if 'submit_business' in request.form:
        if business_form.validate_on_submit():
            current_user.tax_regime = business_form.tax_regime.data
            current_user.default_tax_rate = business_form.default_tax_rate.data
            db.session.commit()
            flash('Configurações tributárias atualizadas!', 'success')
            return redirect(url_for('settings.index'))
        else:
            # DEBUG: Mostra no terminal por que falhou (ex: "Campo Obrigatório")
            logger.warning("Falha ao salvar config fiscal: %s", business_form.errors)

    # Preenchimento inicial (GET)
    if request.method == 'GET':
        account_form.name.data = current_user.name
        account_form.email.data = current_user.email

        # Preenche os dados fiscais atuais do banco
        business_form.tax_regime.data = current_user.tax_regime
        business_form.default_tax_rate.data = current_user.default_tax_rate

        # Preenche webhook
        webhook_form.webhook_url.data = current_user.webhook_url or ''

    return render_template('settings.html',
                           form=account_form,
                           password_form=password_form,
                           business_form=business_form,
                           webhook_form=webhook_form)


@settings_bp.post('/settings/webhook/test')
@login_required
def test_webhook():
    """Dispara payload de teste para a URL de webhook configurada."""
    from app.notifications.webhook import send_test_webhook

    url = current_user.webhook_url
    if not url:
        return jsonify({"ok": False, "error": "Nenhuma URL de webhook configurada."}), 400

    ok = send_test_webhook(url=url, user_id=current_user.id)
    if ok:
        return jsonify({"ok": True, "message": "Webhook de teste enviado com sucesso."})
    return jsonify({"ok": False, "error": "Falha ao enviar webhook. Verifique a URL e tente novamente."}), 502


@settings_bp.post('/settings/api-key/regenerate')
@login_required
def regenerate_api_key():
    if g.is_demo:
        return jsonify({"ok": False, "error": "Conta demo — API key não pode ser alterada."}), 403
    new_key = current_user.generate_api_key()
    db.session.commit()
    return jsonify({"ok": True, "api_key": new_key})


@settings_bp.route('/settings/confirm_email/<token>')
@login_required
def confirm_email_update(token):
    s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    try:
        data = s.loads(token, salt='email-update', max_age=3600)
        new_email = data.get('new_email', '').strip().lower()
        token_user_id = data.get('user_id')
    except Exception:
        flash('Link inválido ou expirado.', 'danger')
        return redirect(url_for('settings.index'))

    if token_user_id != current_user.id:
        flash('Link inválido.', 'danger')
        return redirect(url_for('settings.index'))

    from app.models.user import User
    if db.session.scalar(db.select(User).filter_by(email=new_email)):
        flash('Este e-mail já está em uso.', 'danger')
        return redirect(url_for('settings.index'))

    current_user.email = new_email
    db.session.commit()
    flash('E-mail atualizado com sucesso!', 'success')
    return redirect(url_for('settings.index'))
