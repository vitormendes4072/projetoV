# app/models/custo_fixo_pagamento.py
from datetime import datetime
from app import db


class CustoFixoPagamento(db.Model):
    __tablename__ = "custos_fixos_pagamentos"

    id = db.Column(db.Integer, primary_key=True)

    custo_fixo_id = db.Column(
        db.Integer,
        db.ForeignKey("custos_fixos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    ano = db.Column(db.Integer, nullable=False, index=True)
    mes = db.Column(db.Integer, nullable=False, index=True)

    pago_em = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("custo_fixo_id", "ano", "mes", name="uq_custo_fixo_mes"),
    )

    def __repr__(self) -> str:
        return f"<CustoFixoPagamento custo_fixo_id={self.custo_fixo_id} {self.mes:02d}/{self.ano}>"
