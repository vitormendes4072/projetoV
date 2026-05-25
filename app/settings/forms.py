# app/settings/forms.py
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, PasswordField, SelectField, FloatField # <--- Adicione PasswordField
from wtforms.validators import DataRequired, Email, Length, ValidationError, EqualTo, InputRequired, Optional
from flask_login import current_user
from app import db
from app.models.user import User

class UpdateAccountForm(FlaskForm):
    name = StringField('Nome Completo', validators=[DataRequired(), Length(min=2, max=100)])
    email = StringField('E-mail', validators=[DataRequired(), Email()])

    # NOVO CAMPO DE SEGURANÇA
    current_password = PasswordField('Digite sua senha atual para confirmar', validators=[DataRequired()])

    submit = SubmitField('Salvar Alterações')

    def validate_email(self, email):
        if email.data != current_user.email:
            user = db.session.scalar(db.select(User).filter_by(email=email.data))
            if user:
                raise ValidationError('Este e-mail já está em uso por outra conta.')

class ChangePasswordForm(FlaskForm):
    current_password = PasswordField('Senha Atual', validators=[DataRequired()])
    new_password = PasswordField('Nova Senha', validators=[
        DataRequired(),
        Length(min=8, message="A nova senha deve ter no mínimo 8 caracteres.")
    ])
    confirm_password = PasswordField('Confirmar Nova Senha', validators=[
        DataRequired(),
        EqualTo('new_password', message='As senhas não conferem.')
    ])
    submit_password = SubmitField('Atualizar Senha')

class WebhookForm(FlaskForm):
    webhook_url = StringField(
        'URL do Webhook',
        validators=[Optional(), Length(max=500)],
        description='Suporta Discord, Slack e URLs genéricas (apenas https://).',
    )
    submit_webhook = SubmitField('Salvar Webhook')

    def validate_webhook_url(self, field: StringField) -> None:  # type: ignore[override]
        if field.data and not field.data.startswith("https://"):
            raise ValidationError("Apenas URLs https:// são aceitas.")


class BusinessSettingsForm(FlaskForm):
    tax_regime = SelectField('Regime Tributário', choices=[
        ('simples', 'Simples Nacional'),
        ('mei', 'MEI (Microempreendedor Individual)'),
        ('presumido', 'Lucro Presumido'),
        ('real', 'Lucro Real')
    ])

    # 2. Use InputRequired aqui. Ele permite o valor 0.0!
    default_tax_rate = FloatField('Alíquota Padrão de Imposto (%)', validators=[InputRequired()])

    submit_business = SubmitField('Salvar Configuração Fiscal')
