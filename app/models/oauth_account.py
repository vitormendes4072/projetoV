"""
app/models/oauth_account.py
───────────────────────────
Vincula uma conta OAuth de um provider externo a um User local.
Um usuário pode ter múltiplos OAuthAccounts (Google + GitHub, por exemplo).
"""
from __future__ import annotations

from app import db


class OAuthAccount(db.Model):
    __tablename__ = "oauth_accounts"

    id = db.Column(db.Integer, primary_key=True)

    # FK para o usuário local — cascade garante limpeza ao deletar conta
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # "google" | "github"
    provider = db.Column(db.String(50), nullable=False)

    # ID único do usuário no provider (sub do Google, id numérico do GitHub)
    provider_user_id = db.Column(db.String(256), nullable=False)

    # Cada (provider, provider_user_id) mapeia para exatamente um usuário local
    __table_args__ = (
        db.UniqueConstraint("provider", "provider_user_id", name="uq_oauth_provider_uid"),
    )

    user = db.relationship("User", backref=db.backref("oauth_accounts", lazy="select"))

    def __repr__(self) -> str:
        return f"<OAuthAccount {self.provider}:{self.provider_user_id}>"
