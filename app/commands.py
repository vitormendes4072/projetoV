# app/commands.py
from datetime import date, datetime, timedelta
import click

from flask import Flask

from app.financeiro.alerts_custos_fixos import send_custos_fixos_alerts_for_day

DEMO_EMAIL = "demo@demo.app"

_PRODUCTS = [
    dict(name="Fone de Ouvido Bluetooth", sku="FON-BT-001", cost=45.00, price=129.99, packaging_cost=2.50, stock_quantity=25),
    dict(name="Capa para iPhone 15",      sku="CAP-IP15",   cost=8.50,  price=34.99,  packaging_cost=0.80, stock_quantity=150),
    dict(name="Suporte para Notebook",    sku="SUP-NB-01",  cost=32.00, price=89.99,  packaging_cost=3.00, stock_quantity=18),
    dict(name="Carregador USB-C 65W",     sku="CAR-65W",    cost=28.00, price=79.99,  packaging_cost=1.50, stock_quantity=42),
    dict(name="Mouse Sem Fio",            sku="MSE-WL-01",  cost=22.00, price=69.99,  packaging_cost=1.20, stock_quantity=8),
    dict(name="Webcam HD 1080p",          sku="WEB-HD-01",  cost=55.00, price=159.99, packaging_cost=4.00, stock_quantity=5),
    dict(name="Hub USB 7 Portas",         sku="HUB-USB-7",  cost=18.00, price=49.99,  packaging_cost=1.00, stock_quantity=0),
    dict(name="Teclado Mecânico RGB",     sku="TEC-MEC-01", cost=89.00, price=249.99, packaging_cost=5.00, stock_quantity=3),
]

# (title, price, cost, fba_fee, referral_fee, tax_rate, marketing, net_profit, margin, roi, days_ago)
_SIMULATIONS = [
    ("Fone BT - Cenário Base",     129.99, 45.00, 12.00, 5.00, 4.00, 5.00, 32.57, 25.1, 57.0, 90),
    ("Fone BT - Preço Alto",       149.99, 45.00, 13.00, 5.00, 4.00, 5.00, 47.97, 32.0, 76.5, 88),
    ("Capa iPhone - Margem OK",     34.99,  8.50,  4.00, 5.00, 4.00, 2.00,  9.93, 28.4, 78.1, 85),
    ("Suporte NB - Cenário Base",   89.99, 32.00,  9.00, 5.00, 4.00, 3.00, 22.39, 24.9, 49.9, 82),
    ("Carregador - Promoção",       69.99, 28.00,  7.00, 5.00, 4.00, 0.00, 12.19, 17.4, 30.0, 78),
    ("Carregador - Preço Normal",   79.99, 28.00,  8.00, 5.00, 4.00, 3.00, 16.79, 21.0, 40.0, 75),
    ("Mouse - Cenário Base",        69.99, 22.00,  7.00, 5.00, 4.00, 2.00, 17.19, 24.6, 52.2, 70),
    ("Webcam - Lançamento",        159.99, 55.00, 15.00, 5.00, 4.00, 8.00, 38.79, 24.2, 48.5, 65),
    ("Hub USB - Margem Baixa",      49.99, 18.00,  5.00, 5.00, 4.00, 2.00,  9.99, 20.0, 36.6, 60),
    ("Teclado - Premium",          249.99, 89.00, 22.00, 5.00, 4.00, 8.00, 68.99, 27.6, 55.1, 55),
    ("Fone BT - Desconto 10%",     116.99, 45.00, 11.00, 5.00, 4.00, 0.00, 24.97, 21.3, 43.3, 50),
    ("Capa iPhone - Atacado",       28.99,  8.50,  3.50, 5.00, 4.00, 0.00,  5.78, 19.9, 40.3, 45),
    ("Suporte NB - Promoção",       79.99, 32.00,  8.00, 5.00, 4.00, 0.00, 16.79, 21.0, 37.9, 40),
    ("Mouse - Kit Escritório",      64.99, 22.00,  7.00, 5.00, 4.00, 0.00, 11.39, 17.5, 32.7, 35),
    ("Webcam - Promoção Flash",    139.99, 55.00, 14.00, 5.00, 4.00, 0.00, 17.59, 12.6, 22.7, 30),
    ("Hub USB - Bundle",            44.99, 18.00,  5.00, 5.00, 4.00, 0.00,  5.19, 11.5, 18.5, 25),
    ("Teclado - Promoção",         219.99, 89.00, 20.00, 5.00, 4.00, 0.00, 42.79, 19.5, 35.0, 20),
    ("Carregador - Preço Mínimo",   59.99, 28.00,  6.00, 5.00, 4.00, 0.00,  5.59,  9.3, 13.5, 15),
    ("Fone BT - Margem Negativa",   89.99, 45.00,  9.00, 5.00, 4.00, 5.00, -7.41, -8.2, -11.0, 10),
    ("Fone BT - Recuperação",      119.99, 45.00, 11.00, 5.00, 4.00, 3.00, 27.79, 23.2, 45.3,  3),
]

_CUSTOS_FIXOS = [
    dict(nome="Aluguel do Galpão",     categoria="Infraestrutura",  valor_mensal=2800.00, dia_pagamento=5),
    dict(nome="Frete e Logística",     categoria="Logística",       valor_mensal=1200.00, dia_pagamento=10),
    dict(nome="Software de Gestão",    categoria="Tecnologia",      valor_mensal=350.00,  dia_pagamento=15),
    dict(nome="Honorários Contador",   categoria="Administrativo",  valor_mensal=800.00,  dia_pagamento=20),
]


def _do_seed_demo():
    from app import db
    from app.models.user import User
    from app.models.product import Product, ProductHistory
    from app.models.pricing import PricingHistory
    from app.models.custo_fixo import CustoFixo

    existing = db.session.scalar(db.select(User).filter_by(email=DEMO_EMAIL))
    if existing:
        db.session.delete(existing)
        db.session.commit()

    user = User(email=DEMO_EMAIL, name="Conta Demo", confirmed=True, default_tax_rate=4.0)
    user.set_password("demo-senha-nao-usada")
    db.session.add(user)
    db.session.flush()

    today = date.today()
    now = datetime.now()

    # Produtos
    products = []
    for i, data in enumerate(_PRODUCTS):
        p = Product(user_id=user.id, **data)
        p.created_at = now - timedelta(days=95 - i * 2)
        p.updated_at = p.created_at
        db.session.add(p)
        products.append(p)
    db.session.flush()

    # Histórico de produtos (criação + algumas edições)
    for i, p in enumerate(products):
        db.session.add(ProductHistory(
            product_id=p.id, user_id=user.id,
            price=float(p.price), cost=float(p.cost),
            stock_quantity=p.stock_quantity,
            action_type="Criação Inicial",
            changed_at=p.created_at,
        ))
    # Edições em alguns produtos
    edits = [
        (0, "Edição de Preço",  45, 30),
        (2, "Edição de Estoque", 20, 28),
        (4, "Edição de Preço",   10, 14),
        (6, "Edição de Estoque",  7,  7),
    ]
    for idx, action, stock, days in edits:
        p = products[idx]
        db.session.add(ProductHistory(
            product_id=p.id, user_id=user.id,
            price=float(p.price), cost=float(p.cost),
            stock_quantity=stock,
            action_type=action,
            changed_at=now - timedelta(days=days),
        ))

    # Simulações de precificação
    for title, price, cost, fba, ref, tax, mkt, net, margin, roi, days in _SIMULATIONS:
        db.session.add(PricingHistory(
            user_id=user.id, title=title,
            price=price, cost=cost, fba_fee=fba,
            referral_fee=ref, tax_rate=tax, marketing=mkt,
            net_profit=net, margin=margin, roi=roi,
            created_at=now - timedelta(days=days),
        ))

    # Custos fixos
    for data in _CUSTOS_FIXOS:
        db.session.add(CustoFixo(
            user_id=user.id,
            data_inicio=today.replace(day=1),
            ativo=True,
            **data,
        ))

    db.session.commit()
    return user.id


def _fetch_all_amazon_connections():
    """Retorna todas as AmazonConnection do banco.

    Função auxiliar separada para facilitar mock nos testes
    (AmazonConnection usa schema="public", inexistente no SQLite).
    """
    from app import db
    from app.models.amazon import AmazonConnection
    return db.session.scalars(db.select(AmazonConnection)).all()


def register_commands(app: Flask) -> None:
    @app.cli.command("send-alerts")
    @click.option("--date", "date_str", default="", help="Data no formato YYYY-MM-DD (opcional).")
    @click.option("--dry-run", is_flag=True, help="Não envia e-mail, só mostra o que faria.")
    def send_alerts_cmd(date_str: str, dry_run: bool):
        """Envia alertas de custos fixos por e-mail."""
        run_day = None
        if date_str:
            try:
                run_day = date.fromisoformat(date_str)
            except Exception:
                raise click.ClickException("Data inválida. Use YYYY-MM-DD.")
        summary = send_custos_fixos_alerts_for_day(run_day=run_day, dry_run=dry_run)
        click.echo(summary)

    @app.cli.command("seed-demo")
    def seed_demo_cmd():
        """Cria (ou recria) a conta demo com dados fictícios."""
        user_id = _do_seed_demo()
        click.echo(f"Conta demo criada. email={DEMO_EMAIL}  user_id={user_id}")

    @app.cli.command("amazon-daily-sync")
    @click.option("--dry-run", is_flag=True, help="Lista conexões sem enfileirar jobs.")
    @click.option("--days", default=1, show_default=True, help="Janela de sync em dias.")
    def amazon_daily_sync_cmd(dry_run: bool, days: int):
        """Enfileira job_sync_full para cada usuário com integração Amazon ativa.

        Projetado para execução diária via cron externo (Render Cron Jobs,
        Heroku Scheduler, crontab):

            0 3 * * *  flask amazon-daily-sync

        Com --dry-run lista as conexões sem enfileirar nada.
        """
        import logging
        log = logging.getLogger(__name__)

        conns = _fetch_all_amazon_connections()

        if not conns:
            click.echo("amazon-daily-sync: nenhuma conexão Amazon encontrada. 0 jobs enfileirados.")
            return

        if dry_run:
            click.echo(f"[dry-run] {len(conns)} conexão(ões) encontrada(s) — nenhum job enfileirado:")
            for conn in conns:
                click.echo(f"  user_id={conn.user_id}  conn_id={conn.id}  marketplace={conn.marketplace_id}")
            return

        from app.integrations.amazon.jobs import job_sync_full

        queue = app.extensions["rq_queue"]
        enqueued = 0
        for conn in conns:
            job = queue.enqueue(job_sync_full, conn.user_id, conn.id, days, job_timeout=600)
            log.info("amazon-daily-sync: enfileirado user_id=%s conn_id=%s job_id=%s", conn.user_id, conn.id, job.id)
            click.echo(f"  enfileirado user_id={conn.user_id}  conn_id={conn.id}  job_id={job.id}")
            enqueued += 1

        click.echo(f"amazon-daily-sync: {enqueued} job(s) enfileirado(s).")
