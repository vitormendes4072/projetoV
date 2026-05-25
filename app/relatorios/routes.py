from __future__ import annotations

from datetime import date

from flask import Blueprint, render_template, request, redirect, url_for, send_file, flash
from flask_login import login_required, current_user

from app.relatorios.service import get_monthly_report, available_months
from app.relatorios.pdf_builder import build_monthly_pdf
from app.services.sku_chart import get_sku_scatter_real, get_sku_scatter_estimado

relatorios_bp = Blueprint("relatorios", __name__, url_prefix="/relatorios")


def _parse_mes(mes_str: str | None) -> tuple[int, int]:
    """Converte 'YYYY-MM' para (year, month). Usa mês atual como fallback."""
    today = date.today()
    if mes_str:
        try:
            parts = mes_str.split("-")
            return int(parts[0]), int(parts[1])
        except (ValueError, IndexError):
            pass
    return today.year, today.month


@relatorios_bp.get("/")
@login_required
def index():
    """Redireciona para o relatório do mês atual."""
    today = date.today()
    return redirect(url_for("relatorios.mensal", mes=f"{today.year}-{today.month:02d}"))


@relatorios_bp.get("/mensal")
@login_required
def mensal():
    """Página HTML com preview do relatório mensal de margem."""
    year, month = _parse_mes(request.args.get("mes"))
    report = get_monthly_report(current_user.id, year, month)
    months = available_months(current_user.id)
    current_mes = f"{year}-{month:02d}"
    return render_template(
        "relatorios/mensal.html",
        report=report,
        months=months,
        current_mes=current_mes,
    )


@relatorios_bp.get("/mensal/pdf")
@login_required
def mensal_pdf():
    """Gera e devolve o PDF do relatório mensal."""
    year, month = _parse_mes(request.args.get("mes"))
    report = get_monthly_report(current_user.id, year, month)

    buffer = build_monthly_pdf(report)  # io.BytesIO, seeked to 0

    month_names = [
        "", "jan", "fev", "mar", "abr", "mai", "jun",
        "jul", "ago", "set", "out", "nov", "dez",
    ]
    filename = f"ventregaz_relatorio_{month_names[month]}{year}.pdf"

    # send_file lê o BytesIO em chunks e seta Content-Length automaticamente,
    # sem copiar os bytes para um objeto bytes intermediário.
    return send_file(
        buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )


@relatorios_bp.get("/sku")
@login_required
def sku_scatter():
    """Scatter plot de margem real × volume por SKU."""
    period = request.args.get("period", "all")
    if period not in ("30d", "90d", "all"):
        period = "all"

    real_points = get_sku_scatter_real(current_user.id, period)
    estimado_points = get_sku_scatter_estimado(current_user.id)

    return render_template(
        "relatorios/sku_scatter.html",
        real_points=real_points,
        estimado_points=estimado_points,
        period=period,
    )
