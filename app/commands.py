# app/commands.py
from datetime import date
import click

from flask import Flask

from app.financeiro.alerts_custos_fixos import send_custos_fixos_alerts_for_day


def register_commands(app: Flask) -> None:
    @app.cli.command("send-alerts")
    @click.option("--date", "date_str", default="", help="Data no formato YYYY-MM-DD (opcional).")
    @click.option("--dry-run", is_flag=True, help="Não envia e-mail, só mostra o que faria.")
    def send_alerts_cmd(date_str: str, dry_run: bool):
        """
        Envia alertas de custos fixos por e-mail (de acordo com as configurações do usuário).
        """
        run_day = None
        if date_str:
            try:
                run_day = date.fromisoformat(date_str)
            except Exception:
                raise click.ClickException("Data inválida. Use YYYY-MM-DD.")

        summary = send_custos_fixos_alerts_for_day(run_day=run_day, dry_run=dry_run)
        click.echo(summary)
