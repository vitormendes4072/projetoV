import marshmallow as ma


# ---------------------------------------------------------------------------
# Query args
# ---------------------------------------------------------------------------

class SyncQueryArgsSchema(ma.Schema):
    days = ma.fields.Int(
        load_default=30,
        metadata={"description": "Número de dias retroativos para sincronizar"},
    )


# ---------------------------------------------------------------------------
# Job responses
# ---------------------------------------------------------------------------

class JobQueuedSchema(ma.Schema):
    ok = ma.fields.Bool()
    job_id = ma.fields.Str()
    status = ma.fields.Str()


class JobStatusSchema(ma.Schema):
    ok = ma.fields.Bool()
    job_id = ma.fields.Str()
    status = ma.fields.Str()
    result = ma.fields.Raw(
        allow_none=True,
        metadata={"description": "Resultado quando o job finaliza com sucesso"},
    )
    error = ma.fields.Str(
        allow_none=True,
        metadata={"description": "Mensagem de erro quando o job falha"},
    )


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

class InventorySyncResultSchema(ma.Schema):
    ok = ma.fields.Bool()
    inserted = ma.fields.Int()
    updated = ma.fields.Int()
    total = ma.fields.Int()


# ---------------------------------------------------------------------------
# Profit
# ---------------------------------------------------------------------------

class ProfitResultSchema(ma.Schema):
    ok = ma.fields.Bool()
    amazon_order_id = ma.fields.Str(allow_none=True)
    revenue = ma.fields.Float(allow_none=True)
    amazon_fees = ma.fields.Float(allow_none=True)
    product_cost = ma.fields.Float(allow_none=True)
    tax = ma.fields.Float(allow_none=True)
    profit = ma.fields.Float(allow_none=True)
    margin_pct = ma.fields.Float(allow_none=True)
    mode = ma.fields.Str(allow_none=True)
    message = ma.fields.Str(allow_none=True)


# ---------------------------------------------------------------------------
# Alertas
# ---------------------------------------------------------------------------

class AlertaEnabledBodySchema(ma.Schema):
    enabled = ma.fields.Bool(
        required=True,
        metadata={"description": "True para ativar alertas, False para desativar"},
    )


class AlertaEnabledResultSchema(ma.Schema):
    ok = ma.fields.Bool()
    enabled = ma.fields.Bool()


class AlertaRecipientBodySchema(ma.Schema):
    email = ma.fields.Email(
        required=True,
        metadata={"description": "Endereço de email do destinatário"},
    )


class AlertaRecipientResultSchema(ma.Schema):
    ok = ma.fields.Bool()
    id = ma.fields.Int()
    email = ma.fields.Str()
    enabled = ma.fields.Bool()
