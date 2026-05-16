"""add_cascade_delete_user_products

Revision ID: 74a02d0193bd
Revises: 79aaa8e7f5f5
Create Date: 2026-05-16 18:09:03.544014

"""
from alembic import op
import sqlalchemy as sa

revision = '74a02d0193bd'
down_revision = '79aaa8e7f5f5'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.drop_constraint('products_user_id_fkey', type_='foreignkey')
        batch_op.create_foreign_key(
            'products_user_id_fkey', 'users', ['user_id'], ['id'], ondelete='CASCADE'
        )

    with op.batch_alter_table('product_history', schema=None) as batch_op:
        batch_op.drop_constraint('product_history_product_id_fkey', type_='foreignkey')
        batch_op.create_foreign_key(
            'product_history_product_id_fkey', 'products', ['product_id'], ['id'], ondelete='CASCADE'
        )

    with op.batch_alter_table('pricing_history', schema=None) as batch_op:
        batch_op.drop_constraint('pricing_history_user_id_fkey', type_='foreignkey')
        batch_op.create_foreign_key(
            'pricing_history_user_id_fkey', 'users', ['user_id'], ['id'], ondelete='CASCADE'
        )


def downgrade():
    with op.batch_alter_table('pricing_history', schema=None) as batch_op:
        batch_op.drop_constraint('pricing_history_user_id_fkey', type_='foreignkey')
        batch_op.create_foreign_key(
            'pricing_history_user_id_fkey', 'users', ['user_id'], ['id']
        )

    with op.batch_alter_table('product_history', schema=None) as batch_op:
        batch_op.drop_constraint('product_history_product_id_fkey', type_='foreignkey')
        batch_op.create_foreign_key(
            'product_history_product_id_fkey', 'products', ['product_id'], ['id']
        )

    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.drop_constraint('products_user_id_fkey', type_='foreignkey')
        batch_op.create_foreign_key(
            'products_user_id_fkey', 'users', ['user_id'], ['id']
        )
