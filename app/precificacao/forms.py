# app/precificacao/forms.py
from flask_wtf import FlaskForm
from wtforms import FloatField, SubmitField, StringField
from wtforms.validators import DataRequired, Length

class CalculatorForm(FlaskForm):
    title = StringField('Nome da Simulação (Opcional)', validators=[Length(max=50)], render_kw={"placeholder": "Ex: Teste Preço Alto"})
    price = FloatField('Preço de Venda (R$)', validators=[DataRequired()])
    cost = FloatField('Custo do Produto (R$)', validators=[DataRequired()])
    
    # Taxas da Amazon
    fba_fee = FloatField('Tarifa FBA (Logística Fixa)', validators=[DataRequired()], description="Ex: 15.90")
    referral_fee = FloatField('Comissão Amazon (%)', default=15.0, validators=[DataRequired()])
    
    # Outros custos
    tax_rate = FloatField('Imposto / DAS (%)', default=4.0, validators=[DataRequired()])
    marketing = FloatField('Ads / Marketing (R$)', default=0.0)
    
    submit = SubmitField('Calcular Lucro')
    save = SubmitField('Salvar no Histórico')