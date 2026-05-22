# app/models/pricing.py
from app import db
from datetime import datetime

class PricingHistory(db.Model):
    __tablename__ = 'pricing_history'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete="CASCADE"), nullable=False, index=True)

    # Produto vinculado (opcional) — permite cruzar margem estimada x real
    product_id = db.Column(
        db.Integer,
        db.ForeignKey('products.id', ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    product = db.relationship('Product', lazy='select')

    # Identificação (Opcional)
    title = db.Column(db.String(100), nullable=True, default="Simulação")

    # Inputs (O que ele digitou)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    cost = db.Column(db.Numeric(10, 2), nullable=False)
    fba_fee = db.Column(db.Numeric(10, 2), nullable=False)
    referral_fee = db.Column(db.Numeric(5, 2), nullable=False)
    tax_rate = db.Column(db.Numeric(5, 2), nullable=False)
    marketing = db.Column(db.Numeric(10, 2), default=0.0)

    # Outputs (O resultado)
    net_profit = db.Column(db.Numeric(10, 2), nullable=False)
    margin = db.Column(db.Numeric(5, 2), nullable=False)
    roi = db.Column(db.Numeric(5, 2), nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.now)

    def __repr__(self):
        return f'<PricingHistory {self.title} - {self.price}>'
