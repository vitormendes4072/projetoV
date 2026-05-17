"""amazon: converter user_id de TEXT para INTEGER com FK

Revision ID: 0330b700c2c8
Revises: 74a02d0193bd
Create Date: 2026-05-17

Converte user_id TEXT → INTEGER em 6 tabelas Amazon e adiciona FK para users.id.
Os valores armazenados eram sempre str(user.id), portanto o USING é seguro.
"""
from alembic import op

revision = '0330b700c2c8'
down_revision = '74a02d0193bd'
branch_labels = None
depends_on = None

TABLES = [
    "amazon_connections",
    "amazon_orders",
    "amazon_order_items",
    "amazon_financial_events",
    "amazon_sku_links",
    "amazon_inventory_snapshots",
]

FK_NAME = {
    "amazon_connections":       "fk_amazon_connections_user_id",
    "amazon_orders":            "fk_amazon_orders_user_id",
    "amazon_order_items":       "fk_amazon_order_items_user_id",
    "amazon_financial_events":  "fk_amazon_financial_events_user_id",
    "amazon_sku_links":         "fk_amazon_sku_links_user_id",
    "amazon_inventory_snapshots": "fk_amazon_inventory_snapshots_user_id",
}


def upgrade():
    for table in TABLES:
        # 1. Converte TEXT → INTEGER (USING faz o cast; falha se houver valor não-numérico)
        op.execute(
            f"ALTER TABLE public.{table} "
            f"ALTER COLUMN user_id TYPE INTEGER USING user_id::INTEGER"
        )
        # 2. Adiciona FK para users.id com CASCADE
        op.execute(
            f"ALTER TABLE public.{table} "
            f"ADD CONSTRAINT {FK_NAME[table]} "
            f"FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE"
        )


def downgrade():
    for table in reversed(TABLES):
        # Remove FK
        op.execute(
            f"ALTER TABLE public.{table} "
            f"DROP CONSTRAINT IF EXISTS {FK_NAME[table]}"
        )
        # Reverte INTEGER → TEXT
        op.execute(
            f"ALTER TABLE public.{table} "
            f"ALTER COLUMN user_id TYPE TEXT USING user_id::TEXT"
        )
