"""
app/estoque/routes.py
─────────────────────
Inventory health dashboard — /estoque/
"""
from __future__ import annotations

from flask import Blueprint, render_template
from flask_login import current_user, login_required

from app.services.estoque import get_estoque_data

estoque_bp = Blueprint("estoque", __name__, url_prefix="/estoque")


@estoque_bp.get("/")
@login_required
def index():
    data = get_estoque_data(current_user.id)
    return render_template("estoque/index.html", **data)
