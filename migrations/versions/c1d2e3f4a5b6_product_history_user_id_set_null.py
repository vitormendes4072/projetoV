"""product_history user_id FK ondelete SET NULL

Revision ID: c1d2e3f4a5b6
Revises: b7e3f1a2c4d5
Create Date: 2026-05-20

Adiciona ON DELETE SET NULL na FK product_history.user_id → users.id
para permitir deleção de usuário sem violar a constraint.
"""
from alembic import op

revision = "c1d2e3f4a5b6"
down_revision = "b7e3f1a2c4d5"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("product_history", schema=None) as batch_op:
        batch_op.drop_constraint("product_history_user_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "product_history_user_id_fkey",
            "users",
            ["user_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade():
    with op.batch_alter_table("product_history", schema=None) as batch_op:
        batch_op.drop_constraint("product_history_user_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "product_history_user_id_fkey",
            "users",
            ["user_id"],
            ["id"],
        )
