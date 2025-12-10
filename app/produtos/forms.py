# app/produtos/forms.py
from flask_wtf import FlaskForm
from wtforms import StringField, FloatField, IntegerField, SubmitField
from wtforms.validators import DataRequired, Length, ValidationError
from app.models.product import Product

class ProductForm(FlaskForm):
    name = StringField('Nome do Produto', validators=[DataRequired(), Length(min=2, max=200)])
    sku = StringField('SKU (Código Interno)', validators=[DataRequired(), Length(max=50)])
    asin = StringField('ASIN (Amazon)', validators=[Length(max=20)])
    
    price = FloatField('Preço de Venda (R$)', validators=[DataRequired()])
    cost = FloatField('Custo de Aquisição (R$)', validators=[DataRequired()])
    stock_quantity = IntegerField('Estoque Atual', default=0)
    image_url = StringField('URL da Imagem (Opcional)')
    submit = SubmitField('Salvar Produto')

    # --- NOVO CÓDIGO AQUI ---
    def __init__(self, original_sku=None, *args, **kwargs):
        super(ProductForm, self).__init__(*args, **kwargs)
        self.original_sku = original_sku

    def validate_sku(self, sku):
        # Se o SKU digitado for IGUAL ao original (estou apenas editando preço, por exemplo)
        # então não faz a validação de duplicidade.
        if self.original_sku and sku.data == self.original_sku:
            return

        # Se for diferente, verifica se já existe outro produto com esse SKU
        product = Product.query.filter_by(sku=sku.data).first()
        if product:
            raise ValidationError('Este SKU já está cadastrado.')