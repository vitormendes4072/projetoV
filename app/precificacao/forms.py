# app/precificacao/forms.py
from flask_wtf import FlaskForm
from wtforms import FloatField, SubmitField, StringField
from wtforms.validators import DataRequired, Length, NumberRange, Optional

class CalculatorForm(FlaskForm):
    title = StringField('Nome da Simulação (Opcional)', validators=[Length(max=50)], render_kw={"placeholder": "Ex: Teste Preço Alto"})
    price = FloatField('Preço de Venda (R$)', validators=[
        DataRequired(),
        NumberRange(min=0.01, max=1_000_000, message="O preço deve estar entre R$ 0,01 e R$ 1.000.000.")
    ])
    cost = FloatField('Custo do Produto (R$)', validators=[
        DataRequired(),
        NumberRange(min=0.01, max=1_000_000, message="O custo deve estar entre R$ 0,01 e R$ 1.000.000.")
    ])

    # Taxas da Amazon
    fba_fee = FloatField('Tarifa FBA (Logística Fixa)', validators=[
        DataRequired(),
        NumberRange(min=0, max=10_000, message="A tarifa FBA deve estar entre R$ 0 e R$ 10.000.")
    ], description="Ex: 15.90")
    referral_fee = FloatField('Comissão Amazon (%)', default=15.0, validators=[
        DataRequired(),
        NumberRange(min=0, max=100, message="A comissão deve estar entre 0%% e 100%%.")
    ])

    # Outros custos
    tax_rate = FloatField('Imposto / DAS (%)', default=4.0, validators=[
        DataRequired(),
        NumberRange(min=0, max=100, message="O imposto deve estar entre 0%% e 100%%.")
    ])
    marketing = FloatField('Ads / Marketing (R$)', default=0.0, validators=[
        Optional(),
        NumberRange(min=0, max=1_000_000, message="O orçamento de ads deve ser maior ou igual a zero.")
    ])

    submit = SubmitField('Calcular Lucro')
    save = SubmitField('Salvar no Histórico')