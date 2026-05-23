# app/models/user.py
import secrets
from datetime import datetime, timezone

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

    # --- API KEY ---
    api_key = db.Column(db.String(64), unique=True, nullable=True, index=True)

    # --- SEGURANÇA: invalida tokens de reset após troca de senha ---
    # Carimbado em set_password(); reset_token rejeita tokens emitidos antes deste timestamp.
    password_changed_at = db.Column(db.DateTime(timezone=True), nullable=True)

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

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        # Truncado a segundos para alinhar com a precisão dos tokens itsdangerous.
        # Tokens emitidos ANTES desta marca são inválidos após a troca de senha.
        now = datetime.now(timezone.utc)
        self.password_changed_at = now.replace(microsecond=0)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def generate_api_key(self) -> str:
        """Gera e persiste uma nova API key segura. Retorna a key gerada."""
        self.api_key = secrets.token_urlsafe(32)
        return self.api_key

    def __repr__(self):
        return f"<User {self.email}>"

    custos_fixos = db.relationship(
        "CustoFixo",
        backref="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="select",
    )

