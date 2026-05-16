"""notification_log due_date dedupe by due_date

Revision ID: a80b5afbcd91
Revises: d847c2b92ad1
Create Date: 2026-01-17 14:37:59.786853

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a80b5afbcd91'
down_revision = 'd847c2b92ad1'
branch_labels = None
depends_on = None


def upgrade():
    # 1) Adiciona due_date como NULL (temporário) pra conseguir backfill
    op.add_column("notification_log", sa.Column("due_date", sa.Date(), nullable=True))

    # 2) Backfill: calcula a due_date usando ano/mes do log + dia_pagamento do custos_fixos
    #    Safe day: se dia_pagamento > último dia do mês, usa o último dia.
    op.execute("""
        UPDATE notification_log nl
        SET due_date = (
            make_date(nl.ano, nl.mes, 1)
            + (LEAST(
                  COALESCE(cf.dia_pagamento, 1),
                  EXTRACT(day FROM (date_trunc('month', make_date(nl.ano, nl.mes, 1)) + interval '1 month - 1 day'))
               )::int - 1) * interval '1 day'
        )::date
        FROM custos_fixos cf
        WHERE cf.id = nl.custo_fixo_id
          AND nl.due_date IS NULL
          AND nl.ano IS NOT NULL
          AND nl.mes IS NOT NULL;
    """)

    # Se por algum motivo sobrar due_date NULL (log antigo “estranho”), tenta fallback pro 1º dia do mês
    op.execute("""
        UPDATE notification_log
        SET due_date = make_date(ano, mes, 1)
        WHERE due_date IS NULL AND ano IS NOT NULL AND mes IS NOT NULL;
    """)

    # 3) Agora sim: due_date vira NOT NULL
    op.alter_column("notification_log", "due_date", existing_type=sa.Date(), nullable=False)

    # 4) Remove a unique antiga e cria a nova
    op.drop_constraint("uq_notification_dedupe", "notification_log", type_="unique")
    op.create_unique_constraint(
        "uq_notification_dedupe",
        "notification_log",
        ["user_id", "custo_fixo_id", "due_date", "alert_type"],
    )

    # 5) Index due_date (se o autogenerate já criou, isso pode duplicar; então só cria se NÃO existir)
    op.create_index("ix_notification_log_due_date", "notification_log", ["due_date"], unique=False)

    # 6) (Opcional / recomendado) Deixar ano/mes como NULLABLE.
    # Se o autogenerate já colocou isso, ótimo. Se não colocou, pode manter assim:
    op.alter_column("notification_log", "ano", existing_type=sa.Integer(), nullable=True)
    op.alter_column("notification_log", "mes", existing_type=sa.Integer(), nullable=True)


def downgrade():
    # Reverte index e constraint nova
    op.drop_index("ix_notification_log_due_date", table_name="notification_log")

    op.drop_constraint("uq_notification_dedupe", "notification_log", type_="unique")
    op.create_unique_constraint(
        "uq_notification_dedupe",
        "notification_log",
        ["user_id", "custo_fixo_id", "ano", "mes", "alert_type"],
    )

    # Remove coluna due_date
    op.drop_column("notification_log", "due_date")

    # Reverte ano/mes para NOT NULL (se era assim antes; se não quiser, pode tirar)
    op.alter_column("notification_log", "ano", existing_type=sa.Integer(), nullable=False)
    op.alter_column("notification_log", "mes", existing_type=sa.Integer(), nullable=False)
