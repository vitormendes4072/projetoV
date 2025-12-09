from app import db

class Product(db.Model):
    __tablename__ = 'products'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    
    # Campos da Amazon (Performance: Indexados para busca rápida)
    sku = db.Column(db.String(50), index=True)  # Seu código interno
    asin = db.Column(db.String(20), index=True) # Código da Amazon
    
    # Financeiro
    price = db.Column(db.Float, nullable=False) # Preço de Venda
    cost = db.Column(db.Float, nullable=False)  # Custo de Aquisição
    stock_quantity = db.Column(db.Integer, default=0)
    
    # Chave Estrangeira (Segurança: Produto TEM que ter um dono)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    def __repr__(self):
        return f'<Product {self.sku} - {self.name}>'
    
    # Método auxiliar para calcular lucro rápido
    def calculate_profit(self):
        return self.price - self.cost