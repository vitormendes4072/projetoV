# app/models/user.py
from app import db, login_manager
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=True)

    # index=True melhora performance no login
    email = db.Column(db.String(150), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    confirmed = db.Column(db.Boolean, default=False, nullable=False)

    # --- CAMPOS TRIBUTÁRIOS ---
    tax_regime = db.Column(db.String(50), nullable=True)
    default_tax_rate = db.Column(db.Numeric(5, 2), default=4.0)

    # Relacionamento: um usuário tem muitos produtos
    products = db.relationship(
        "Product",
        backref="owner",
        lazy="select",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    pricing_history = db.relationship(
        "PricingHistory",
        backref="user",
        lazy="select",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # Relacionamento 1:1 com credenciais Amazon
    amazon_credentials = db.relationship(
        "AmazonCredentials",
        uselist=False,
        backref="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User {self.email}>"
    
    custos_fixos = db.relationship(
        "CustoFixo",
        backref="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="select",
    )

