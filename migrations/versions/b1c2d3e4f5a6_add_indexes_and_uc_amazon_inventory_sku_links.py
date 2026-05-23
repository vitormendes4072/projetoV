"""add indexes and unique constraints to amazon_inventory_snapshots and amazon_sku_links

Revision ID: b1c2d3e4f5a6
Revises: 03425978f8e0
Create Date: 2026-05-22

Problema: amazon_inventory_snapshots e amazon_sku_links não tinham índices
em user_id nem UniqueConstraints — cada sync podia inserir linhas duplicadas
e toda query multi-tenant fazia full-scan.

Correções:
  - amazon_inventory_snapshots:
      UniqueConstraint(user_id, marketplace_id, seller_sku) — garante idempotência do sync
      Index(user_id, seller_sku)                            — acelera queries de lookup
  - amazon_sku_links:
      UniqueConstraint(user_id, amazon_seller_sku)          — um SKU vinculado a um único produto por usuário
      Index(user_id)                                        — acelera queries multi-tenant
"""
from alembic import op

revision = 'b1c2d3e4f5a6'
down_revision = '03425978f8e0'
branch_labels = None
depends_on = None


def upgrade():
    # ------------------------------------------------------------------
    # amazon_inventory_snapshots (schema public)
    # ------------------------------------------------------------------
    op.create_index(
        'ix_amazon_inventory_user_sku',
        'amazon_inventory_snapshots',
        ['user_id', 'seller_sku'],
        schema='public',
    )
    op.create_unique_constraint(
        'uq_amazon_inventory_user_marketplace_sku',
        'amazon_inventory_snapshots',
        ['user_id', 'marketplace_id', 'seller_sku'],
        schema='public',
    )

    # ------------------------------------------------------------------
    # amazon_sku_links (schema public)
    # ------------------------------------------------------------------
    op.create_index(
        'ix_amazon_sku_links_user_id',
        'amazon_sku_links',
        ['user_id'],
        schema='public',
    )
    op.create_unique_constraint(
        'uq_amazon_sku_links_user_seller_sku',
        'amazon_sku_links',
        ['user_id', 'amazon_seller_sku'],
        schema='public',
    )


def downgrade():
    op.drop_constraint(
        'uq_amazon_sku_links_user_seller_sku',
        'amazon_sku_links',
        schema='public',
        type_='unique',
    )
    op.drop_index(
        'ix_amazon_sku_links_user_id',
        table_name='amazon_sku_links',
        schema='public',
    )
    op.drop_constraint(
        'uq_amazon_inventory_user_marketplace_sku',
        'amazon_inventory_snapshots',
        schema='public',
        type_='unique',
    )
    op.drop_index(
        'ix_amazon_inventory_user_sku',
        table_name='amazon_inventory_snapshots',
        schema='public',
    )
