from __future__ import annotations

from datetime import date

from flask import Blueprint, render_template, request, redirect, url_for, make_response, flash
from flask_login import login_required, current_user

from app.relatorios.service import get_monthly_report, available_months
from app.relatorios.pdf_builder import build_monthly_pdf

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

    pdf_bytes = build_monthly_pdf(report)

    month_names = [
        "", "jan", "fev", "mar", "abr", "mai", "jun",
        "jul", "ago", "set", "out", "nov", "dez",
    ]
    filename = f"ventregaz_relatorio_{month_names[month]}{year}.pdf"

    response = make_response(pdf_bytes)
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
