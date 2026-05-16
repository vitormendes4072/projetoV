# app/precificacao/forms.py
from flask_wtf import FlaskForm
from wtforms import FloatField, SubmitField, StringField
# IMPORTANTE: Adicione InputRequired e Optional
from wtforms.validators import DataRequired, Length, InputRequired, Optional

class CalculatorForm(FlaskForm):
    # Identificação
    title = StringField('Nome da Simulação (Opcional)', validators=[Length(max=50)], render_kw={"placeholder": "Ex: Teste Preço Alto"})
    
    # Preço e Custo (Aceitam 0, mas InputRequired exige que digite algo)
    price = FloatField('Preço de Venda (R$)', validators=[InputRequired()])
    cost = FloatField('Custo do Produto (R$)', validators=[InputRequired()])
    
    # Taxas (AQUI ESTAVA O PROBLEMA DO ZERO)
    # Agora com InputRequired(), se você digitar 0, ele aceita!
    fba_fee = FloatField('Tarifa FBA (Logística Fixa)', validators=[InputRequired()], description="Ex: 15.90")
    referral_fee = FloatField('Comissão Amazon (%)', default=15.0, validators=[InputRequired()])
    
    tax_rate = FloatField('Imposto / DAS (%)', default=4.0, validators=[InputRequired()])
    
    # Marketing é opcional. Se deixar vazio, vira None/0
    marketing = FloatField('Ads / Marketing (R$)', default=0.0, validators=[Optional()])
    
    submit = SubmitField('Calcular')
    save = SubmitField('Salvar no Histórico')