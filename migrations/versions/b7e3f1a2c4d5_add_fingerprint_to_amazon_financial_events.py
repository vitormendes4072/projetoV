"""add fingerprint to amazon_financial_events

Revision ID: b7e3f1a2c4d5
Revises: 0330b700c2c8
Create Date: 2026-05-18

Adiciona coluna fingerprint (sha256 truncado a 64 chars) com índice único parcial
em (user_id, fingerprint) WHERE fingerprint IS NOT NULL.
O índice parcial garante que eventos históricos sem fingerprint não sejam afetados.
"""
from alembic import op
import sqlalchemy as sa

revision = "b7e3f1a2c4d5"
down_revision = "0330b700c2c8"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "amazon_financial_events",
        sa.Column("fingerprint", sa.String(64), nullable=True),
        schema="public",
    )
    op.create_index(
        "uq_amazon_financial_events_user_fp",
        "amazon_financial_events",
        ["user_id", "fingerprint"],
        unique=True,
        schema="public",
        postgresql_where=sa.text("fingerprint IS NOT NULL"),
    )


def downgrade():
    op.drop_index(
        "uq_amazon_financial_events_user_fp",
        table_name="amazon_financial_events",
        schema="public",
    )
    op.drop_column("amazon_financial_events", "fingerprint", schema="public")
