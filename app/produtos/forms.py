# app/produtos/forms.py
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed, FileRequired
from wtforms import StringField, FloatField, IntegerField, SubmitField
from wtforms.validators import DataRequired, Length, ValidationError, Optional, NumberRange
from flask_login import current_user
from app.models.product import Product

class ProductForm(FlaskForm):
    name = StringField('Nome do Produto', validators=[DataRequired(), Length(min=2, max=200)])
    sku = StringField('SKU (Código Interno)', validators=[DataRequired(), Length(max=50)])

    price = FloatField('Preço de referência (opcional)', validators=[Optional(), NumberRange(min=0)], default=0.0)
    cost = FloatField('Custo de Aquisição (R$)', validators=[DataRequired()])
    packaging_cost = FloatField('Custo de Embalagem (R$)', validators=[Optional(), NumberRange(min=0)], default=0.0)

    stock_quantity = IntegerField('Estoque Atual', default=0)
    image_url = StringField('URL da Imagem (Opcional)')
    submit = SubmitField('Salvar Produto')

    # --- NOVO CÓDIGO AQUI ---
    def __init__(self, original_sku=None, *args, **kwargs):
        super(ProductForm, self).__init__(*args, **kwargs)
        self.original_sku = original_sku

    def validate_sku(self, sku):
        if self.original_sku and sku.data == self.original_sku:
            return

        product = Product.query.filter_by(
            sku=sku.data,
            user_id=current_user.id
        ).first()
        if product:
            raise ValidationError('Este SKU já está cadastrado para sua conta.')


class CsvUploadForm(FlaskForm):
    arquivo = FileField('Arquivo CSV', validators=[
        FileRequired(message='Selecione um arquivo CSV.'),
        FileAllowed(['csv'], message='Apenas arquivos .csv são permitidos.'),
    ])
    submit = SubmitField('Importar')
