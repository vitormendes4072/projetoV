# app/models/custo_fixo.py
from datetime import datetime, date
from app import db


class CustoFixo(db.Model):
    __tablename__ = "custos_fixos"

    id = db.Column(db.Integer, primary_key=True)

    # Multiusuário (cada user tem seus próprios custos)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    nome = db.Column(db.String(120), nullable=False)
    categoria = db.Column(db.String(60), nullable=False, default="Outros")

    # Money: Numeric é melhor do que Float
    valor_mensal = db.Column(db.Numeric(12, 2), nullable=False, default=0)

    # Dia do mês em que normalmente paga (1–31). Ex: 5, 10, 20
    dia_pagamento = db.Column(db.Integer, nullable=True)

    __table_args__ = (
        db.CheckConstraint("dia_pagamento IS NULL OR (dia_pagamento >= 1 AND dia_pagamento <= 31)", name="ck_custos_fixos_dia_pagamento"),
    )

    pagamentos = db.relationship(
        "CustoFixoPagamento",
        backref="custo_fixo",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )



    # Vigência (para manter histórico quando valor mudar)
    data_inicio = db.Column(db.Date, nullable=False, default=date.today)
    data_fim = db.Column(db.Date, nullable=True)

    ativo = db.Column(db.Boolean, nullable=False, default=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def vigente_em(self, ano: int, mes: int) -> bool:
        """True se este custo vale para a competência (ano/mes)."""
        inicio_ok = (self.data_inicio.year, self.data_inicio.month) <= (ano, mes)
        fim_ok = True
        if self.data_fim:
            fim_ok = (self.data_fim.year, self.data_fim.month) >= (ano, mes)
        return bool(self.ativo and inicio_ok and fim_ok)

    def __repr__(self) -> str:
        return f"<CustoFixo user_id={self.user_id} nome={self.nome} valor={self.valor_mensal}>"
