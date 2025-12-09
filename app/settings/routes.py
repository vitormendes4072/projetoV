# app/settings/routes.py
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from flask_mail import Message
from threading import Thread
from itsdangerous import URLSafeTimedSerializer
from app import db, mail
from .forms import UpdateAccountForm

settings_bp = Blueprint('settings', __name__)

# --- FUNÇÃO AUXILIAR DE ENVIO DE E-MAIL ---
def send_async_email(app, msg):
    with app.app_context():
        try:
            mail.send(msg)
        except Exception as e:
            print(f"ERRO EMAIL SETTINGS: {e}")

def send_update_email(user, new_email):
    s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    # Geramos um token contendo o NOVO e-mail dentro dele
    token = s.dumps({'new_email': new_email}, salt='email-update')
    
    msg = Message('Confirme seu novo E-mail - Marketplace Manager',
                  sender='noreply@demo.com', recipients=[new_email])
    
    link = url_for('settings.confirm_email_update', token=token, _external=True)
    
    msg.body = f'''Olá, {user.name}!
Recebemos um pedido para alterar o e-mail da sua conta para este endereço.

Para confirmar essa mudança, clique no link abaixo:
{link}

Se não foi você, ignore este e-mail. Sua conta permanece segura com o e-mail antigo.
'''
    # Envia em background
    Thread(target=send_async_email, args=(current_app._get_current_object(), msg)).start()

# --- ROTAS ---

@settings_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def index():
    form = UpdateAccountForm()
    
    if form.validate_on_submit():
        # 1. Verifica Senha (Segurança)
        if not current_user.check_password(form.current_password.data):
            flash('Senha incorreta. Alterações canceladas.', 'danger')
            return render_template('settings.html', form=form)
        
        # 2. Atualiza o NOME imediatamente (não precisa de confirmação)
        if form.name.data != current_user.name:
            current_user.name = form.name.data
            db.session.commit()
            flash('Nome atualizado com sucesso!', 'success')

        # 3. Lógica do E-MAIL (Segurança Crítica)
        if form.email.data != current_user.email:
            # NÃO salvamos no banco ainda!
            # Enviamos o e-mail para o endereço NOVO para ver se ele existe/pertence ao usuário
            send_update_email(current_user, form.email.data)
            flash(f'Um link de confirmação foi enviado para {form.email.data}. O e-mail da conta só mudará após você clicar no link.', 'info')
        
        return redirect(url_for('settings.index'))
    
    elif request.method == 'GET':
        form.name.data = current_user.name
        form.email.data = current_user.email
        
    return render_template('settings.html', form=form)

@settings_bp.route('/settings/confirm_email/<token>')
@login_required
def confirm_email_update(token):
    s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    try:
        # Tenta ler o token e extrair o email (expira em 1 hora)
        data = s.loads(token, salt='email-update', max_age=3600)
        new_email = data.get('new_email')
    except:
        flash('O link de confirmação é inválido ou expirou.', 'danger')
        return redirect(url_for('settings.index'))
    
    # Verifica se esse email já não foi pego por outro usuário nesse meio tempo
    from app.models.user import User # Importação local para evitar ciclo
    if User.query.filter_by(email=new_email).first():
        flash('Este e-mail já está sendo usado por outra conta.', 'danger')
        return redirect(url_for('settings.index'))
    
    # AGORA SIM: Atualiza o banco de dados
    current_user.email = new_email
    # Opcional: Re-confirmar a conta se quiser, mas assumimos que o link prova existência
    current_user.confirmed = True 
    db.session.commit()
    
    flash('Seu e-mail foi atualizado com sucesso!', 'success')
    return redirect(url_for('settings.index'))