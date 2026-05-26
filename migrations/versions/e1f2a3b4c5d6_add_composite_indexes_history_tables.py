"""add composite indexes on history tables

Adiciona índices compostos em tabelas de histórico para eliminar sorts
em memória nas queries mais frequentes:

  pricing_history  (user_id, created_at)      → dashboard / relatorios / comparativo
  product_history  (product_id, changed_at)   → historico_produto (listagem + gráfico)
  product_history  (user_id, changed_at)      → dashboard recent_changes
  notification_log (user_id, sent_at)         → queries de log por usuário

Revision ID: a1b2c3d4e5f6
Revises: c2d3e4f5a6b7
Create Date: 2026-05-24 00:00:00.000000

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'e1f2a3b4c5d6'
down_revision = 'd1e2f3a4b5c6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        'ix_pricing_history_user_created',
        'pricing_history',
        ['user_id', 'created_at'],
    )
    op.create_index(
        'ix_product_history_product_changed',
        'product_history',
        ['product_id', 'changed_at'],
    )
    op.create_index(
        'ix_product_history_user_changed',
        'product_history',
        ['user_id', 'changed_at'],
    )
    op.create_index(
        'ix_notification_log_user_sent',
        'notification_log',
        ['user_id', 'sent_at'],
    )


def downgrade():
    op.drop_index('ix_notification_log_user_sent', table_name='notification_log')
    op.drop_index('ix_product_history_user_changed', table_name='product_history')
    op.drop_index('ix_product_history_product_changed', table_name='product_history')
    op.drop_index('ix_pricing_history_user_created', table_name='pricing_history')
