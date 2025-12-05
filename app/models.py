from . import db, login_manager
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=True) # <--- NOVO CAMPO
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)

    # Por padrão, todo mundo nasce como "False" (Não confirmado)
    confirmed = db.Column(db.Boolean, default=False, nullable=False)

    # Método para definir a senha (Cria o Hash)
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    # Método para verificar a senha (Compara Hash)
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)