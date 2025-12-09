import os
from dotenv import load_dotenv

# Carrega o .env se ele existir (útil para dev local)
load_dotenv()

class Config:
    """Configurações Base (Comuns a todos os ambientes)"""
    # Se não tiver SECRET_KEY em produção, isso é uma falha grave. 
    # Usamos o 'get' mas o ideal em produção é garantir que ela exista.
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'voce-esqueceu-de-configurar-a-chave'
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Configurações de Email
    MAIL_SERVER = os.environ.get('MAIL_SERVER')
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 587) # O 'or' dentro do int evita erro de conversão
    # O .lower() garante que 'True', 'true' ou 'TRUE' funcionem
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'False').lower() == 'true'
    MAIL_USE_SSL = os.environ.get('MAIL_USE_SSL', 'False').lower() == 'true'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')

class DevelopmentConfig(Config):
    """Configurações só para o seu PC"""
    DEBUG = True
    # Se não tiver banco configurado, usa um SQLite local temporário para não quebrar
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', '').replace("postgres://", "postgresql://") or 'sqlite:///dev.db'

class ProductionConfig(Config):
    """Configurações para o Servidor Real"""
    DEBUG = False
    # Em produção, se não tiver banco, é melhor quebrar o erro na cara para avisar
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', '').replace("postgres://", "postgresql://")

# Dicionário para facilitar a escolha
config_options = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}