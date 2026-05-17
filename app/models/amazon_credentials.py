# app/models/amazon_credentials.py
from datetime import datetime
from app import db
from app.utils.crypto import encrypt, decrypt


class AmazonCredentials(db.Model):
    __tablename__ = "amazon_credentials"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True
    )

    seller_id = db.Column(db.String(50), nullable=True)

    client_id = db.Column(db.String(200), nullable=True)

    # ✅ Armazenados criptografados no banco
    client_secret_enc = db.Column(db.Text, nullable=True)
    refresh_token_enc = db.Column(db.Text, nullable=True)

    marketplace_region = db.Column(db.String(30), nullable=True, default="BR")

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # ---------- Properties (API limpa) ----------
    @property
    def client_secret(self) -> str | None:
        return decrypt(self.client_secret_enc)

    @client_secret.setter
    def client_secret(self, value: str | None) -> None:
        self.client_secret_enc = encrypt(value)

    @property
    def refresh_token(self) -> str | None:
        return decrypt(self.refresh_token_enc)

    @refresh_token.setter
    def refresh_token(self, value: str | None) -> None:
        self.refresh_token_enc = encrypt(value)

    def __repr__(self) -> str:
        return f"<AmazonCredentials user_id={self.user_id}>"
