from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from dotenv import load_dotenv
from flask_mail import Mail
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_talisman import Talisman
import os

# Carrega variáveis do .env
load_dotenv()

db = SQLAlchemy()
login_manager = LoginManager()
mail = Mail()

# Configura o Limiter para usar a memória do PC por enquanto (storage_uri="memory://")
# O key_func=get_remote_address diz que vamos bloquear por IP
limiter = Limiter(key_func=get_remote_address, storage_uri="memory://")

def create_app():
    app = Flask(__name__)
    
    # Configurações de Segurança e Banco
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
    # Ajuste para SQLAlchemy (Supabase usa postgresql://)
    if os.getenv('DATABASE_URL'):
        app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL').replace("postgres://", "postgresql://")
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # ### ADICIONADO: CONFIGURAÇÃO DO EMAIL ###
    # Sem isso, o Flask ignora seu .env e tenta conectar localmente
    app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER')
    app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587)) # Converte para número inteiro
    app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS') == 'True' # Converte texto para Booleano
    app.config['MAIL_USE_SSL'] = os.getenv('MAIL_USE_SSL') == 'True'
    app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
    app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
    # #######################################

    db.init_app(app)
    mail.init_app(app)
    limiter.init_app(app)
    
    # Configuração do Login
    login_manager.init_app(app)
    login_manager.login_view = 'main.login' # Nome da função da rota de login
    login_manager.login_message = 'Por favor, faça login para acessar.'

    # ---------------------------------------------------------
    # CONFIGURAÇÃO DE SEGURANÇA (TALISMAN)
    # ---------------------------------------------------------
    
    # Política de Segurança de Conteúdo (CSP)
    csp = {
        'default-src': '\'self\'',
        'script-src': [
            '\'self\'',
            'https://cdn.jsdelivr.net', # Bootstrap JS
            'https://cdnjs.cloudflare.com' # Outras libs comuns
        ],
        'script-src': [
            '\'self\'',
            'https://cdn.tailwindcss.com', # <--- O motor do Tailwind
            '\'unsafe-eval\'' # Necessário para o Tailwind via CDN em desenvolvimento
        ],
        'style-src': [
            '\'self\'',
            '\'unsafe-inline\'', # Permite estilos na tag <style>
            'https://fonts.googleapis.com', # Fontes do Google
            'https://cdn.jsdelivr.net', # Bootstrap CSS
            'https://cdnjs.cloudflare.com'
        ],
        'font-src': [
            '\'self\'',
            'https://fonts.gstatic.com'
        ],
        'img-src': ['\'self\'', 'data:'] # Permite imagens locais e base64 (SVGs)
    }

    # Mantemos a lógica: Se for Debug, relaxa. Se não, aplica a regra acima.
    if app.debug:
        # Se mesmo com app.debug o CSS sumiu, force o content_security_policy=None aqui
        Talisman(app, force_https=False, content_security_policy=None)
        print("--- MODO DEBUG: Talisman Desativado ---")
    else:
        Talisman(app, content_security_policy=csp)

    from .routes import main
    app.register_blueprint(main)

    with app.app_context():
        db.create_all() # Cria as tabelas no Supabase se não existirem

    # Personaliza o erro 429 (Muitas Requisições)
    @app.errorhandler(429)
    def ratelimit_handler(e):
        return render_template('429.html', error=e), 429

    return app