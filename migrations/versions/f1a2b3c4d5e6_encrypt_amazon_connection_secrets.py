"""encrypt AmazonConnection secrets — retire dead AmazonCredentials table

Revision ID: f1a2b3c4d5e6
Revises: c1d2e3f4a5b6
Create Date: 2026-05-21

Substitui as colunas plaintext lwa_client_secret, lwa_refresh_token e
aws_secret_access_key em amazon_connections por colunas _enc criptografadas
via Fernet (app.utils.crypto). Remove a tabela amazon_credentials que era
código morto (existia no banco mas nenhuma rota a populava).

ATENÇÃO: defina CREDENTIALS_ENCRYPTION_KEY antes de rodar esta migration
para que credenciais existentes sejam migradas automaticamente. Sem a chave,
as colunas enc ficam NULL e o usuário deve reconectar via /connect.
"""
from alembic import op
import sqlalchemy as sa

revision = 'f1a2b3c4d5e6'
down_revision = 'c1d2e3f4a5b6'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Adiciona colunas criptografadas em amazon_connections
    op.add_column('amazon_connections',
                  sa.Column('lwa_client_secret_enc', sa.Text(), nullable=True),
                  schema='public')
    op.add_column('amazon_connections',
                  sa.Column('lwa_refresh_token_enc', sa.Text(), nullable=True),
                  schema='public')
    op.add_column('amazon_connections',
                  sa.Column('aws_secret_access_key_enc', sa.Text(), nullable=True),
                  schema='public')

    # 2. Migra dados existentes (requer CREDENTIALS_ENCRYPTION_KEY)
    # Se a chave não estiver disponível, enc columns ficam NULL —
    # usuário precisa reconectar via /connect após a migration.
    try:
        from app.utils.crypto import encrypt
        bind = op.get_bind()
        rows = bind.execute(sa.text(
            "SELECT id, lwa_client_secret, lwa_refresh_token, aws_secret_access_key "
            "FROM public.amazon_connections"
        )).fetchall()
        for row in rows:
            bind.execute(sa.text(
                "UPDATE public.amazon_connections "
                "SET lwa_client_secret_enc    = :s, "
                "    lwa_refresh_token_enc    = :r, "
                "    aws_secret_access_key_enc = :a "
                "WHERE id = CAST(:id AS UUID)"
            ), {
                "s": encrypt(row.lwa_client_secret),
                "r": encrypt(row.lwa_refresh_token),
                "a": encrypt(row.aws_secret_access_key),
                "id": str(row.id),
            })
    except RuntimeError:
        # CREDENTIALS_ENCRYPTION_KEY ausente — dados existentes não migrados
        pass

    # 3. Remove colunas plaintext de amazon_connections
    op.drop_column('amazon_connections', 'lwa_client_secret', schema='public')
    op.drop_column('amazon_connections', 'lwa_refresh_token', schema='public')
    op.drop_column('amazon_connections', 'aws_secret_access_key', schema='public')

    # 4. Remove tabela amazon_credentials (código morto — nenhuma rota a usava)
    op.drop_table('amazon_credentials')


def downgrade():
    # Recria tabela amazon_credentials (vazia — nunca foi populada por rotas)
    op.create_table(
        'amazon_credentials',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('seller_id', sa.String(length=50), nullable=True),
        sa.Column('client_id', sa.String(length=200), nullable=True),
        sa.Column('client_secret_enc', sa.Text(), nullable=True),
        sa.Column('refresh_token_enc', sa.Text(), nullable=True),
        sa.Column('marketplace_region', sa.String(length=30), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id'),
    )

    # Restaura colunas plaintext
    op.add_column('amazon_connections',
                  sa.Column('lwa_client_secret', sa.String(), nullable=True),
                  schema='public')
    op.add_column('amazon_connections',
                  sa.Column('lwa_refresh_token', sa.String(), nullable=True),
                  schema='public')
    op.add_column('amazon_connections',
                  sa.Column('aws_secret_access_key', sa.String(), nullable=True),
                  schema='public')

    # Descriptografa de volta (best-effort — requer chave)
    try:
        from app.utils.crypto import decrypt
        bind = op.get_bind()
        rows = bind.execute(sa.text(
            "SELECT id, lwa_client_secret_enc, lwa_refresh_token_enc, aws_secret_access_key_enc "
            "FROM public.amazon_connections"
        )).fetchall()
        for row in rows:
            bind.execute(sa.text(
                "UPDATE public.amazon_connections "
                "SET lwa_client_secret     = :s, "
                "    lwa_refresh_token     = :r, "
                "    aws_secret_access_key = :a "
                "WHERE id = CAST(:id AS UUID)"
            ), {
                "s": decrypt(row.lwa_client_secret_enc),
                "r": decrypt(row.lwa_refresh_token_enc),
                "a": decrypt(row.aws_secret_access_key_enc),
                "id": str(row.id),
            })
    except RuntimeError:
        pass

    # Remove colunas enc
    op.drop_column('amazon_connections', 'lwa_client_secret_enc', schema='public')
    op.drop_column('amazon_connections', 'lwa_refresh_token_enc', schema='public')
    op.drop_column('amazon_connections', 'aws_secret_access_key_enc', schema='public')
