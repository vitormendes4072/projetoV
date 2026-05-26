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
    min_stock = db.Column(db.Integer, nullable=False, default=5)
    image_url = db.Column(db.String(500), nullable=True)

    # Alerta automático de margem — envia e-mail quando a última simulação
    # vinculada ao produto fica abaixo deste threshold (%).
    # None = sem alerta configurado.
    margin_alert_threshold = db.Column(db.Numeric(5, 2), nullable=True)

    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete="CASCADE"), nullable=False, index=True)

    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    # Relacionamento com o histórico (Um produto tem muitos históricos)
    history = db.relationship('ProductHistory', backref='product', lazy='select', cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Product {self.sku}>'

# --- NOVA CLASSE DE HISTÓRICO ---
class ProductHistory(db.Model):
    __tablename__ = 'product_history'
    __table_args__ = (
        # Cobre: WHERE product_id = X ORDER BY changed_at [ASC|DESC]
        # (historico_produto — listagem paginada e série para gráfico)
        db.Index('ix_product_history_product_changed', 'product_id', 'changed_at'),
        # Cobre: WHERE user_id = X ORDER BY changed_at DESC
        # (dashboard — recent_changes)
        db.Index('ix_product_history_user_changed', 'user_id', 'changed_at'),
    )

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete="CASCADE"), nullable=False, index=True)

    price = db.Column(db.Numeric(10, 2))
    cost = db.Column(db.Numeric(10, 2))
    stock_quantity = db.Column(db.Integer)

    action_type = db.Column(db.String(50), nullable=False)

    changed_at = db.Column(db.DateTime, default=datetime.now)

    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete="SET NULL"), nullable=True, index=True)
    user = db.relationship('User')
