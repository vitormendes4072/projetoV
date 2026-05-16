from datetime import datetime
from app import db

class CustoFixoHistory(db.Model):
    __tablename__ = "custos_fixos_history"

    id = db.Column(db.BigInteger, primary_key=True)
    item_id = db.Column(db.BigInteger, nullable=False, index=True)

    action = db.Column(db.String(32), nullable=False)  # create|update|toggle_paid|toggle_active|bulk|delete
    diff = db.Column(db.JSON, nullable=True)
    snapshot = db.Column(db.JSON, nullable=True)
    note = db.Column(db.Text, nullable=True)

    changed_by = db.Column(db.BigInteger, nullable=True, index=True)
    changed_at = db.Column(db.DateTime(timezone=True), nullable=False, default=datetime.utcnow, index=True)

    def __repr__(self):
        return f"<CustoFixoHistory item_id={self.item_id} action={self.action}>"
