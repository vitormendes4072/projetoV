"""add margin_alert_log, weekly_report_log, custos_fixos_history tables

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-05-26

Cria tabelas que existiam no modelo Python mas nunca tiveram migração:
- margin_alert_log: dedupe de alertas de margem por e-mail
- weekly_report_log: dedupe de relatórios semanais por e-mail
- custos_fixos_history: histórico de alterações em custos fixos

Usa IF NOT EXISTS / inspector para ser idempotente — tabelas podem
já existir no Supabase se foram criadas manualmente antes desta migração.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = 'b3c4d5e6f7a8'
down_revision = 'a2b3c4d5e6f7'
branch_labels = None
depends_on = None


def _table_exists(bind, table_name):
    return inspect(bind).has_table(table_name)


def _index_exists(bind, table_name, index_name):
    indexes = {ix['name'] for ix in inspect(bind).get_indexes(table_name)}
    return index_name in indexes


def upgrade():
    bind = op.get_bind()

    # ------------------------------------------------------------------
    # margin_alert_log
    # ------------------------------------------------------------------
    if not _table_exists(bind, 'margin_alert_log'):
        op.create_table(
            'margin_alert_log',
            sa.Column('id', sa.BigInteger(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('product_id', sa.Integer(), nullable=False),
            sa.Column('alert_date', sa.Date(), nullable=False),
            sa.Column('margin_value', sa.Numeric(7, 2), nullable=True),
            sa.Column('sent_at', sa.DateTime(timezone=True),
                      server_default=sa.text('now()'), nullable=False),
            sa.ForeignKeyConstraint(['product_id'], ['products.id'],
                                    ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'],
                                    ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('user_id', 'product_id', 'alert_date',
                                name='uq_margin_alert_dedupe'),
        )
    if not _index_exists(bind, 'margin_alert_log', 'ix_margin_alert_log_user_id'):
        op.create_index('ix_margin_alert_log_user_id',
                        'margin_alert_log', ['user_id'])

    # ------------------------------------------------------------------
    # weekly_report_log
    # ------------------------------------------------------------------
    if not _table_exists(bind, 'weekly_report_log'):
        op.create_table(
            'weekly_report_log',
            sa.Column('id', sa.BigInteger(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('week_start', sa.Date(), nullable=False),
            sa.Column('neg_simulations', sa.Integer(), nullable=False,
                      server_default='0'),
            sa.Column('neg_orders', sa.Integer(), nullable=False,
                      server_default='0'),
            sa.Column('sent_at', sa.DateTime(timezone=True),
                      server_default=sa.text('now()'), nullable=False),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'],
                                    ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('user_id', 'week_start',
                                name='uq_weekly_report_dedupe'),
        )
    if not _index_exists(bind, 'weekly_report_log', 'ix_weekly_report_log_user_id'):
        op.create_index('ix_weekly_report_log_user_id',
                        'weekly_report_log', ['user_id'])

    # ------------------------------------------------------------------
    # custos_fixos_history — item_id e changed_by sem FK (modelo não
    # declara ForeignKey explícita)
    # ------------------------------------------------------------------
    if not _table_exists(bind, 'custos_fixos_history'):
        op.create_table(
            'custos_fixos_history',
            sa.Column('id', sa.BigInteger(), nullable=False),
            sa.Column('item_id', sa.BigInteger(), nullable=False),
            sa.Column('action', sa.String(length=32), nullable=False),
            sa.Column('diff', sa.JSON(), nullable=True),
            sa.Column('snapshot', sa.JSON(), nullable=True),
            sa.Column('note', sa.Text(), nullable=True),
            sa.Column('changed_by', sa.BigInteger(), nullable=True),
            sa.Column('changed_at', sa.DateTime(timezone=True),
                      server_default=sa.text('now()'), nullable=False),
            sa.PrimaryKeyConstraint('id'),
        )
    if not _index_exists(bind, 'custos_fixos_history',
                         'ix_custos_fixos_history_item_id'):
        op.create_index('ix_custos_fixos_history_item_id',
                        'custos_fixos_history', ['item_id'])
    if not _index_exists(bind, 'custos_fixos_history',
                         'ix_custos_fixos_history_changed_by'):
        op.create_index('ix_custos_fixos_history_changed_by',
                        'custos_fixos_history', ['changed_by'])
    if not _index_exists(bind, 'custos_fixos_history',
                         'ix_custos_fixos_history_changed_at'):
        op.create_index('ix_custos_fixos_history_changed_at',
                        'custos_fixos_history', ['changed_at'])


def downgrade():
    op.drop_index('ix_custos_fixos_history_changed_at',
                  table_name='custos_fixos_history')
    op.drop_index('ix_custos_fixos_history_changed_by',
                  table_name='custos_fixos_history')
    op.drop_index('ix_custos_fixos_history_item_id',
                  table_name='custos_fixos_history')
    op.drop_table('custos_fixos_history')

    op.drop_index('ix_weekly_report_log_user_id',
                  table_name='weekly_report_log')
    op.drop_table('weekly_report_log')

    op.drop_index('ix_margin_alert_log_user_id',
                  table_name='margin_alert_log')
    op.drop_table('margin_alert_log')
