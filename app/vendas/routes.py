# app/vendas/routes.py
from flask import Blueprint, render_template, request
from flask_login import login_required, current_user

from app.services.vendas import get_vendas_kpis

vendas_bp = Blueprint("vendas", __name__, url_prefix="/vendas")

_VALID_PERIODS = {"7d", "30d", "90d", "all"}


@vendas_bp.get("/")
@login_required
def index():
    """Sales analytics hub — order KPIs and top SKUs for the selected period."""
    period = request.args.get("period", "30d")
    if period not in _VALID_PERIODS:
        period = "30d"
    kpis = get_vendas_kpis(current_user.id, period)
    return render_template("vendas/index.html", period=period, **kpis)
