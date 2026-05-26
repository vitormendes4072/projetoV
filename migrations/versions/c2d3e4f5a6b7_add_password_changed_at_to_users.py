"""add password_changed_at to users

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-05-22

Adiciona coluna password_changed_at em users para invalidar tokens de reset
de senha após uso. set_password() carimba este timestamp; reset_token rejeita
qualquer token emitido antes ou no momento da última troca de senha.

Sem esta coluna, tokens de reset eram reutilizáveis por até 30 min após uso
(URLSafeTimedSerializer é stateless — não há revogação nativa).
"""
import sqlalchemy as sa
from alembic import op

revision = 'c2d3e4f5a6b7'
down_revision = 'b1c2d3e4f5a6'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'users',
        sa.Column('password_changed_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_column('users', 'password_changed_at')
