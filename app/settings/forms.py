# app/settings/forms.py
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, PasswordField # <--- Adicione PasswordField
from wtforms.validators import DataRequired, Email, Length, ValidationError
from flask_login import current_user
from app.models.user import User

class UpdateAccountForm(FlaskForm):
    name = StringField('Nome Completo', validators=[DataRequired(), Length(min=2, max=100)])
    email = StringField('E-mail', validators=[DataRequired(), Email()])
    
    # NOVO CAMPO DE SEGURANÇA
    current_password = PasswordField('Digite sua senha atual para confirmar', validators=[DataRequired()])
    
    submit = SubmitField('Salvar Alterações')

    def validate_email(self, email):
        if email.data != current_user.email:
            user = User.query.filter_by(email=email.data).first()
            if user:
                raise ValidationError('Este e-mail já está em uso por outra conta.')