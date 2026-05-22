"""add product_id to pricing_history

Revision ID: 03425978f8e0
Revises: 9a946870f3c2
Create Date: 2026-05-22 00:38:50.168763

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '03425978f8e0'
down_revision = '9a946870f3c2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('pricing_history', schema=None) as batch_op:
        batch_op.add_column(sa.Column('product_id', sa.Integer(), nullable=True))
        batch_op.create_index(
            batch_op.f('ix_pricing_history_product_id'), ['product_id'], unique=False
        )
        batch_op.create_foreign_key(
            'fk_pricing_history_product_id',
            'products', ['product_id'], ['id'],
            ondelete='SET NULL',
        )


def downgrade():
    with op.batch_alter_table('pricing_history', schema=None) as batch_op:
        batch_op.drop_constraint('fk_pricing_history_product_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_pricing_history_product_id'))
        batch_op.drop_column('product_id')
