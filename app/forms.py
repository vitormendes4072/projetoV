from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, FloatField
from wtforms.validators import DataRequired, Email, Length, EqualTo, Regexp

class RegistrationForm(FlaskForm):
    name = StringField('Nome', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Senha', validators=[
        DataRequired(),
        # Mínimo 8 caracteres
        Length(min=8, message="Sua senha deve ter pelo menos 8 caracteres."),
        # Regex opcional: Exige 1 letra e 1 número
        # Regexp(r'^(?=.*[A-Za-z])(?=.*\d)[A-Za-z\d]{8,}$', message="Senha deve conter letras e números.")
    ])
    confirm_password = PasswordField('Confirmar Senha', validators=[
        DataRequired(), 
        EqualTo('password', message='As senhas devem ser iguais.')
    ])
    confirm_password = PasswordField('Confirmar Senha', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Cadastrar')

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Senha', validators=[DataRequired()])
    submit = SubmitField('Entrar')

class RequestResetForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    submit = SubmitField('Redefinir Senha')

class ResetPasswordForm(FlaskForm):
    password = PasswordField('Nova Senha', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirmar Senha', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Mudar Senha')

class CalculatorForm(FlaskForm):
    price = FloatField('Preço de Venda (R$)', validators=[DataRequired()])
    cost = FloatField('Custo do Produto (R$)', validators=[DataRequired()])
    
    # Taxas da Amazon
    fba_fee = FloatField('Tarifa FBA (Logística Fixa)', validators=[DataRequired()], description="Ex: 15.90")
    referral_fee = FloatField('Comissão Amazon (%)', default=15.0, validators=[DataRequired()])
    
    # Outros custos
    tax_rate = FloatField('Imposto / DAS (%)', default=4.0, validators=[DataRequired()])
    marketing = FloatField('Ads / Marketing (R$)', default=0.0)
    
    submit = SubmitField('Calcular Lucro')