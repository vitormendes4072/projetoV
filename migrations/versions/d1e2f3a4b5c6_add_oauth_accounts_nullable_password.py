"""add oauth_accounts table, make password_hash nullable

Revision ID: d1e2f3a4b5c6
Revises: c2d3e4f5a6b7
Create Date: 2026-05-26

"""
from alembic import op
import sqlalchemy as sa

revision = 'd1e2f3a4b5c6'
down_revision = 'c2d3e4f5a6b7'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Cria a tabela oauth_accounts
    op.create_table(
        'oauth_accounts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('provider', sa.String(length=50), nullable=False),
        sa.Column('provider_user_id', sa.String(length=256), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('provider', 'provider_user_id', name='uq_oauth_provider_uid'),
    )
    op.create_index('ix_oauth_accounts_user_id', 'oauth_accounts', ['user_id'])

    # 2. Torna password_hash nullable (usuários OAuth não têm senha local)
    op.alter_column('users', 'password_hash', existing_type=sa.String(length=256), nullable=True)


def downgrade():
    # Reverte password_hash para NOT NULL (requer que não haja NULLs)
    op.alter_column('users', 'password_hash', existing_type=sa.String(length=256), nullable=False)

    op.drop_index('ix_oauth_accounts_user_id', table_name='oauth_accounts')
    op.drop_table('oauth_accounts')
