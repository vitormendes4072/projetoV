# app/models/pricing.py
from app import db
from datetime import datetime

class PricingHistory(db.Model):
    __tablename__ = 'pricing_history'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Identificação (Opcional)
    title = db.Column(db.String(100), nullable=True, default="Simulação")
    
    # Inputs (O que ele digitou)
    price = db.Column(db.Float, nullable=False)
    cost = db.Column(db.Float, nullable=False)
    fba_fee = db.Column(db.Float, nullable=False)
    referral_fee = db.Column(db.Float, nullable=False)
    tax_rate = db.Column(db.Float, nullable=False)
    marketing = db.Column(db.Float, default=0.0)
    
    # Outputs (O resultado)
    net_profit = db.Column(db.Float, nullable=False)
    margin = db.Column(db.Float, nullable=False)
    roi = db.Column(db.Float, nullable=False)
    
    created_at = db.Column(db.DateTime, default=datetime.now)

    def __repr__(self):
        return f'<PricingHistory {self.title} - {self.price}>'