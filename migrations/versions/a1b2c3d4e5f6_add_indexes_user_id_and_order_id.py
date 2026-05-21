"""add indexes on user_id and amazon_order_id in core tables

Revision ID: a1b2c3d4e5f6
Revises: f1a2b3c4d5e6
Create Date: 2026-05-21

Adiciona índices nas colunas mais filtradas das tabelas core.
PostgreSQL não cria índice automático em colunas de FK — sem esses índices
toda query multi-tenant (filtrando por user_id) faz full-scan.
"""
from alembic import op

revision = 'a1b2c3d4e5f6'
down_revision = 'f1a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_index('ix_products_user_id', 'products', ['user_id'])
    op.create_index('ix_pricing_history_user_id', 'pricing_history', ['user_id'])
    op.create_index('ix_product_history_product_id', 'product_history', ['product_id'])
    op.create_index('ix_product_history_user_id', 'product_history', ['user_id'])
    op.create_index('ix_amazon_orders_user_id', 'amazon_orders', ['user_id'], schema='public')
    op.create_index('ix_amazon_orders_amazon_order_id', 'amazon_orders', ['amazon_order_id'], schema='public')


def downgrade():
    op.drop_index('ix_amazon_orders_amazon_order_id', table_name='amazon_orders', schema='public')
    op.drop_index('ix_amazon_orders_user_id', table_name='amazon_orders', schema='public')
    op.drop_index('ix_product_history_user_id', table_name='product_history')
    op.drop_index('ix_product_history_product_id', table_name='product_history')
    op.drop_index('ix_pricing_history_user_id', table_name='pricing_history')
    op.drop_index('ix_products_user_id', table_name='products')
