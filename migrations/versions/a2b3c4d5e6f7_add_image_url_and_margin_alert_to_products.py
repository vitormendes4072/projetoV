"""add image_url and margin_alert_threshold to products

Revision ID: a2b3c4d5e6f7
Revises: f2a3b4c5d6e7
Create Date: 2026-05-26

Adiciona colunas faltantes na tabela products:
- image_url (nullable): URL da imagem do produto
- margin_alert_threshold (nullable): threshold de margem para alertas automáticos por e-mail
"""
from alembic import op
import sqlalchemy as sa

revision = 'a2b3c4d5e6f7'
down_revision = 'f2a3b4c5d6e7'
branch_labels = None
depends_on = None


def upgrade():
    # Usa IF NOT EXISTS para ser idempotente — image_url pode já existir
    # no Supabase caso tenha sido adicionada manualmente antes desta migração.
    op.execute(
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS image_url VARCHAR(500)"
    )
    op.execute(
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS "
        "margin_alert_threshold NUMERIC(5, 2)"
    )


def downgrade():
    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.drop_column('margin_alert_threshold')
        batch_op.drop_column('image_url')
