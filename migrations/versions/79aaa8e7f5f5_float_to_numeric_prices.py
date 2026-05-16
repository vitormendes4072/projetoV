"""float_to_numeric_prices

Revision ID: 79aaa8e7f5f5
Revises: 029d8955ef81
Create Date: 2026-05-16 17:37:59.525356

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '79aaa8e7f5f5'
down_revision = '029d8955ef81'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('pricing_history', schema=None) as batch_op:
        batch_op.alter_column('price',
               existing_type=sa.DOUBLE_PRECISION(precision=53),
               type_=sa.Numeric(precision=10, scale=2),
               existing_nullable=False)
        batch_op.alter_column('cost',
               existing_type=sa.DOUBLE_PRECISION(precision=53),
               type_=sa.Numeric(precision=10, scale=2),
               existing_nullable=False)
        batch_op.alter_column('fba_fee',
               existing_type=sa.DOUBLE_PRECISION(precision=53),
               type_=sa.Numeric(precision=10, scale=2),
               existing_nullable=False)
        batch_op.alter_column('referral_fee',
               existing_type=sa.DOUBLE_PRECISION(precision=53),
               type_=sa.Numeric(precision=5, scale=2),
               existing_nullable=False)
        batch_op.alter_column('tax_rate',
               existing_type=sa.DOUBLE_PRECISION(precision=53),
               type_=sa.Numeric(precision=5, scale=2),
               existing_nullable=False)
        batch_op.alter_column('marketing',
               existing_type=sa.DOUBLE_PRECISION(precision=53),
               type_=sa.Numeric(precision=10, scale=2),
               existing_nullable=True)
        batch_op.alter_column('net_profit',
               existing_type=sa.DOUBLE_PRECISION(precision=53),
               type_=sa.Numeric(precision=10, scale=2),
               existing_nullable=False)
        batch_op.alter_column('margin',
               existing_type=sa.DOUBLE_PRECISION(precision=53),
               type_=sa.Numeric(precision=5, scale=2),
               existing_nullable=False)
        batch_op.alter_column('roi',
               existing_type=sa.DOUBLE_PRECISION(precision=53),
               type_=sa.Numeric(precision=5, scale=2),
               existing_nullable=False)

    with op.batch_alter_table('product_history', schema=None) as batch_op:
        batch_op.alter_column('price',
               existing_type=sa.DOUBLE_PRECISION(precision=53),
               type_=sa.Numeric(precision=10, scale=2),
               existing_nullable=True)
        batch_op.alter_column('cost',
               existing_type=sa.DOUBLE_PRECISION(precision=53),
               type_=sa.Numeric(precision=10, scale=2),
               existing_nullable=True)

    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.alter_column('price',
               existing_type=sa.DOUBLE_PRECISION(precision=53),
               type_=sa.Numeric(precision=10, scale=2),
               existing_nullable=False)
        batch_op.alter_column('cost',
               existing_type=sa.DOUBLE_PRECISION(precision=53),
               type_=sa.Numeric(precision=10, scale=2),
               existing_nullable=False)
        batch_op.alter_column('packaging_cost',
               existing_type=sa.NUMERIC(precision=12, scale=2),
               type_=sa.Numeric(precision=10, scale=2),
               existing_nullable=False,
               existing_server_default=sa.text('0'))

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('default_tax_rate',
               existing_type=sa.DOUBLE_PRECISION(precision=53),
               type_=sa.Numeric(precision=5, scale=2),
               existing_nullable=True)


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('default_tax_rate',
               existing_type=sa.Numeric(precision=5, scale=2),
               type_=sa.DOUBLE_PRECISION(precision=53),
               existing_nullable=True)

    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.alter_column('packaging_cost',
               existing_type=sa.Numeric(precision=10, scale=2),
               type_=sa.NUMERIC(precision=12, scale=2),
               existing_nullable=False,
               existing_server_default=sa.text('0'))
        batch_op.alter_column('cost',
               existing_type=sa.Numeric(precision=10, scale=2),
               type_=sa.DOUBLE_PRECISION(precision=53),
               existing_nullable=False)
        batch_op.alter_column('price',
               existing_type=sa.Numeric(precision=10, scale=2),
               type_=sa.DOUBLE_PRECISION(precision=53),
               existing_nullable=False)

    with op.batch_alter_table('product_history', schema=None) as batch_op:
        batch_op.alter_column('cost',
               existing_type=sa.Numeric(precision=10, scale=2),
               type_=sa.DOUBLE_PRECISION(precision=53),
               existing_nullable=True)
        batch_op.alter_column('price',
               existing_type=sa.Numeric(precision=10, scale=2),
               type_=sa.DOUBLE_PRECISION(precision=53),
               existing_nullable=True)

    with op.batch_alter_table('pricing_history', schema=None) as batch_op:
        batch_op.alter_column('roi',
               existing_type=sa.Numeric(precision=5, scale=2),
               type_=sa.DOUBLE_PRECISION(precision=53),
               existing_nullable=False)
        batch_op.alter_column('margin',
               existing_type=sa.Numeric(precision=5, scale=2),
               type_=sa.DOUBLE_PRECISION(precision=53),
               existing_nullable=False)
        batch_op.alter_column('net_profit',
               existing_type=sa.Numeric(precision=10, scale=2),
               type_=sa.DOUBLE_PRECISION(precision=53),
               existing_nullable=False)
        batch_op.alter_column('marketing',
               existing_type=sa.Numeric(precision=10, scale=2),
               type_=sa.DOUBLE_PRECISION(precision=53),
               existing_nullable=True)
        batch_op.alter_column('tax_rate',
               existing_type=sa.Numeric(precision=5, scale=2),
               type_=sa.DOUBLE_PRECISION(precision=53),
               existing_nullable=False)
        batch_op.alter_column('referral_fee',
               existing_type=sa.Numeric(precision=5, scale=2),
               type_=sa.DOUBLE_PRECISION(precision=53),
               existing_nullable=False)
        batch_op.alter_column('fba_fee',
               existing_type=sa.Numeric(precision=10, scale=2),
               type_=sa.DOUBLE_PRECISION(precision=53),
               existing_nullable=False)
        batch_op.alter_column('cost',
               existing_type=sa.Numeric(precision=10, scale=2),
               type_=sa.DOUBLE_PRECISION(precision=53),
               existing_nullable=False)
        batch_op.alter_column('price',
               existing_type=sa.Numeric(precision=10, scale=2),
               type_=sa.DOUBLE_PRECISION(precision=53),
               existing_nullable=False)
