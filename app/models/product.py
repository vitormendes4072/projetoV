# app/models/product.py
from app import db
from datetime import datetime

class Product(db.Model):
    __tablename__ = 'products'
    __table_args__ = (
        db.UniqueConstraint('user_id', 'sku', name='uq_products_user_sku'),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    sku = db.Column(db.String(50), index=True, nullable=False)
    asin = db.Column(db.String(20), index=True, nullable=True)
    
    price = db.Column(db.Numeric(10, 2), nullable=False, default=0.0)
    cost = db.Column(db.Numeric(10, 2), nullable=False, default=0.0)
    packaging_cost = db.Column(db.Numeric(10, 2), nullable=False, default=0.0)
    stock_quantity = db.Column(db.Integer, default=0)
    image_url = db.Column(db.String(500), nullable=True)
    
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete="CASCADE"), nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    # Relacionamento com o histórico (Um produto tem muitos históricos)
    history = db.relationship('ProductHistory', backref='product', lazy='select', cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Product {self.sku}>'

# --- NOVA CLASSE DE HISTÓRICO ---
class ProductHistory(db.Model):
    __tablename__ = 'product_history'

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete="CASCADE"), nullable=False)
    
    # O que mudou? Vamos salvar o estado crítico
    price = db.Column(db.Numeric(10, 2))
    cost = db.Column(db.Numeric(10, 2))
    stock_quantity = db.Column(db.Integer)
    
    # Tipo de mudança: 'Criação' ou 'Edição'
    action_type = db.Column(db.String(50), nullable=False)
    
    changed_at = db.Column(db.DateTime, default=datetime.now)
    
    # Quem mudou? (Útil se tiver vários usuários no futuro)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    user = db.relationship('User')