# app/__init__.py
import os
from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_mail import Mail
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_talisman import Talisman
# Importamos o dicionário de opções que criamos no novo config.py
from config import config_options 

db = SQLAlchemy()
login_manager = LoginManager()
mail = Mail()
limiter = Limiter(key_func=get_remote_address, storage_uri="memory://")

# Define o ambiente padrão (se não tiver no .env, assume 'default' que é desenvolvimento)
env_name = os.environ.get('FLASK_ENV', 'default')

# AQUI ESTAVA O ERRO: Precisamos receber 'config_name' como argumento
def create_app(config_name=env_name):
    app = Flask(__name__)
    
    # Carrega a configuração correta baseada no nome ('development' ou 'production')
    app.config.from_object(config_options[config_name])
    
    # Inicializa Extensões
    db.init_app(app)
    mail.init_app(app)
    limiter.init_app(app)
    login_manager.init_app(app)
    
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Por favor, faça login para acessar.'

    # ---------------------------------------------------------
    # SEGURANÇA (TALISMAN)
    # ---------------------------------------------------------
    csp = {
        'default-src': '\'self\'',
        'script-src': [
            '\'self\'',
            'https://cdn.jsdelivr.net',
            'https://cdnjs.cloudflare.com'
        ],
        'style-src': [
            '\'self\'',
            '\'unsafe-inline\'',
            'https://fonts.googleapis.com',
            'https://cdn.jsdelivr.net',
            'https://cdnjs.cloudflare.com'
        ],
        'font-src': [
            '\'self\'',
            'https://fonts.gstatic.com'
        ],
        'img-src': ['\'self\'', 'data:']
    }

    if app.debug:
        Talisman(app, force_https=False, content_security_policy=None)
    else:
        Talisman(app, content_security_policy=csp)

    # ---------------------------------------------------------
    # BLUEPRINTS
    # ---------------------------------------------------------
    from app.auth.routes import auth
    from app.main.routes import main
    from app.precificacao.routes import pricing
    from app.settings.routes import settings_bp
    from app.produtos.routes import produtos_bp

    app.register_blueprint(auth)
    app.register_blueprint(main)
    app.register_blueprint(pricing)
    app.register_blueprint(settings_bp)
    app.register_blueprint(produtos_bp)

    @app.errorhandler(429)
    def ratelimit_handler(e):
        return render_template('429.html', error=e), 429

    with app.app_context():
        db.create_all()

    return app