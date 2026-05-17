# Ponto de entrada mantido para compatibilidade com app/__init__.py.
# A lógica está em routes_custos.py e routes_alertas.py.
from app.financeiro.routes_custos import financeiro_bp  # noqa: F401
import app.financeiro.routes_alertas  # noqa: F401 — registra rotas de alertas no blueprint
