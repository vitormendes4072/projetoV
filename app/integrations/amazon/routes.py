# app/integrations/amazon/routes.py
import logging
import os
import uuid

logger = logging.getLogger(__name__)
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import Blueprint, request, jsonify, render_template
from flask_login import login_required, current_user

from app import db
from app.models import AmazonConnection, AmazonOrder, AmazonOrderItem
from app.models.amazon_finances import AmazonFinancialEvent
from app.models.amazon_sku_link import AmazonSkuLink
from app.models.product import Product
from app.models.amazon_sku_link import AmazonSkuLink
from app.models.amazon_inventory import AmazonInventorySnapshot
from app.integrations.amazon.service import (
    list_orders,
    list_order_items,
    list_financial_events,
)

amazon = Blueprint("amazon", __name__, url_prefix="/integrations/amazon")

SP_TZ = ZoneInfo("America/Sao_Paulo")


# ---------------------------
# Helpers
# ---------------------------
def user_key() -> str:
    # seu DB está com user_id como TEXT
    return str(current_user.id)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso_z(dt: datetime) -> str:
    """
    Converte datetime para ISO8601 aceito pela Amazon: sem micros + com 'Z' no final.
    """
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def extract_amount_currency(ev: dict):
    """
    Tenta extrair (amount, currency) de múltiplos formatos possíveis do payload.
    Retorna (amount: float|None, currency: str|None)
    """
    candidates = ("FeeAmount", "ChargeAmount", "Amount", "AdjustmentAmount")
    for k in candidates:
        v = ev.get(k)
        if isinstance(v, dict):
            # formatos comuns
            if "CurrencyAmount" in v:
                return v.get("CurrencyAmount"), v.get("CurrencyCode")
            if "Amount" in v:
                return v.get("Amount"), v.get("CurrencyCode")
            if "amount" in v:
                return v.get("amount"), v.get("currencyCode") or v.get("currency")
        # às vezes vem como número direto
        if isinstance(v, (int, float)):
            return v, None
    return None, None


def parse_iso_dt(s: str):
    """
    Parse ISO da Amazon (ex: '2026-01-21T00:00:00Z') para datetime timezone-aware.
    """
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def to_sp(dt):
    return dt.astimezone(SP_TZ) if dt else None


def compute_sync_start(conn: AmazonConnection, days_default: int) -> datetime:
    """
    Janela incremental:
      - se last_sync_at existir => last_sync_at - 2 dias (buffer)
      - senão => agora - days_default
    """
    now = utcnow()
    if getattr(conn, "last_sync_at", None):
        return conn.last_sync_at - timedelta(days=2)
    return now - timedelta(days=days_default)


def dev_guard():
    """
    Bloqueia endpoints DEV fora de ambiente dev.
    """
    dev_only = (os.getenv("DEV_ONLY_ENDPOINTS", "false").lower() == "true")
    flask_env = (os.getenv("FLASK_ENV", "").lower())
    if not dev_only or flask_env not in ("development", "dev"):
        return False
    return True


# ---------------------------
# Status / Connect / Test
# ---------------------------
@amazon.get("/status")
@login_required
def status():
    conn = AmazonConnection.query.filter_by(user_id=user_key()).first()
    if not conn:
        return jsonify({"ok": True, "connected": False})

    return jsonify(
        {
            "ok": True,
            "connected": True,
            "marketplace_id": conn.marketplace_id,
            "last_sync_at": conn.last_sync_at.isoformat() if conn.last_sync_at else None,
        }
    )


@amazon.post("/connect")
@login_required
def connect():
    data = request.get_json(force=True) or {}
    # debug: pode remover depois
    logger.debug("Amazon connect payload: %s", data)

    required = [
        "marketplace_id",
        "lwa_client_id",
        "lwa_client_secret",
        "lwa_refresh_token",
        "aws_access_key_id",
        "aws_secret_access_key",
    ]
    missing = [k for k in required if not data.get(k)]
    if missing:
        return jsonify({"ok": False, "error": f"Faltando: {', '.join(missing)}"}), 400

    conn = AmazonConnection.query.filter_by(user_id=user_key()).first()
    if not conn:
        # força id pra não depender do default do banco
        conn = AmazonConnection(id=uuid.uuid4(), user_id=user_key())

    conn.marketplace_id = data["marketplace_id"].strip()
    conn.seller_id = data.get("seller_id") or None

    conn.lwa_client_id = data["lwa_client_id"].strip()
    conn.lwa_client_secret = data["lwa_client_secret"]
    conn.lwa_refresh_token = data["lwa_refresh_token"]

    conn.aws_access_key_id = data["aws_access_key_id"].strip()
    conn.aws_secret_access_key = data["aws_secret_access_key"]
    conn.aws_region = (data.get("aws_region") or "us-east-1").strip()
    conn.role_arn = data.get("role_arn") or None

    db.session.add(conn)
    db.session.commit()

    return jsonify({"ok": True})


@amazon.post("/test")
@login_required
def test_connection():
    conn = AmazonConnection.query.filter_by(user_id=user_key()).first()
    if not conn:
        return jsonify({"ok": False, "error": "Integração Amazon não configurada"}), 400

    created_after = iso_z(utcnow() - timedelta(days=2))

    try:
        orders = list_orders(conn, created_after_iso=created_after)
        return jsonify({"ok": True, "orders_found": len(orders), "created_after": created_after})
    except Exception as e:
        logger.exception("Erro ao testar conexão Amazon")
        return jsonify({"ok": False, "error": repr(e), "created_after": created_after}), 400


# ---------------------------
# Internal sync implementations
# ---------------------------
def _sync_orders_and_items(conn: AmazonConnection, created_after_iso: str):
    """
    Sync Orders + OrderItems
    Retorna (orders_upserted, items_inserted)
    """
    orders = list_orders(conn, created_after_iso=created_after_iso)

    upserted_orders = 0
    inserted_items = 0

    for o in orders:
        amazon_order_id = o.get("AmazonOrderId")
        if not amazon_order_id:
            continue

        order = AmazonOrder.query.filter_by(user_id=user_key(), amazon_order_id=amazon_order_id).first()
        if not order:
            order = AmazonOrder(
                user_id=user_key(),
                amazon_order_id=amazon_order_id,
                marketplace_id=conn.marketplace_id,
            )

        order.order_status = o.get("OrderStatus")

        dt = parse_iso_dt(o.get("PurchaseDate", ""))
        order.purchase_date = to_sp(dt)

        ot = o.get("OrderTotal") or {}
        order.currency = ot.get("CurrencyCode")
        order.order_total_amount = ot.get("Amount")

        order.raw_json = o
        db.session.add(order)
        upserted_orders += 1

        # itens: reinserir (MVP)
        AmazonOrderItem.query.filter_by(user_id=user_key(), amazon_order_id=amazon_order_id).delete()

        try:
            items = list_order_items(conn, amazon_order_id)
        except Exception as e:
            logger.warning("Falha ao buscar itens do pedido %s: %s", amazon_order_id, e)
            continue

        for it in items:
            ip = it.get("ItemPrice") or {}
            item = AmazonOrderItem(
                user_id=user_key(),
                amazon_order_id=amazon_order_id,
                seller_sku=it.get("SellerSKU"),
                asin=it.get("ASIN"),
                quantity=it.get("QuantityOrdered"),
                item_price=ip.get("Amount"),
                currency=ip.get("CurrencyCode"),
                raw_json=it,
            )
            db.session.add(item)
            inserted_items += 1

    return upserted_orders, inserted_items, len(orders)


def _sync_finances(conn: AmazonConnection, posted_after_iso: str):
    events, _payload = list_financial_events(conn, posted_after_iso=posted_after_iso)
    inserted_events = 0

    seen = set()  # dedupe local por execução

    for event_type, items in events.items():
        if not isinstance(items, list):
            continue

        for ev in items:
            if not isinstance(ev, dict):
                ev = {"value": ev}

            posted_dt = to_sp(parse_iso_dt(ev.get("PostedDate", "")))
            amazon_order_id = ev.get("AmazonOrderId") or ev.get("OrderId")

            amount, currency = extract_amount_currency(ev)

            # fingerprint para evitar duplicata no mesmo payload
            fp = (
                event_type,
                amazon_order_id,
                ev.get("FinancialEventGroupId"),
                ev.get("PostedDate"),
                amount,
                currency,
                ev.get("ShipmentItemId") or ev.get("SellerSKU") or ev.get("ASIN") or ev.get("value"),
            )
            if fp in seen:
                continue
            seen.add(fp)

            fe = AmazonFinancialEvent(
                user_id=user_key(),
                posted_date=posted_dt,
                event_group_id=ev.get("FinancialEventGroupId"),
                amazon_order_id=amazon_order_id,
                event_type=event_type,
                amount=amount,
                currency=currency,
                raw_json=ev,
            )
            db.session.add(fe)
            inserted_events += 1

    return inserted_events



# ---------------------------
# Sync endpoints
# ---------------------------
@amazon.route("/sync_orders_only", methods=["GET", "POST"])
@login_required
def sync_orders_only():
    """
    Sync apenas pedidos (sem itens).
    Útil para popular listagem rapidamente.
    """
    conn = AmazonConnection.query.filter_by(user_id=user_key()).first()
    if not conn:
        return jsonify({"ok": False, "error": "Integração Amazon não configurada"}), 400

    days = int(request.args.get("days", "30"))
    created_after = iso_z(utcnow() - timedelta(days=days))

    try:
        orders = list_orders(conn, created_after_iso=created_after)
    except Exception as e:
        logger.exception("Erro em sync_orders_only")
        return jsonify({"ok": False, "error": repr(e), "created_after": created_after}), 400

    upserted = 0
    for o in orders:
        amazon_order_id = o.get("AmazonOrderId")
        if not amazon_order_id:
            continue

        order = AmazonOrder.query.filter_by(user_id=user_key(), amazon_order_id=amazon_order_id).first()
        if not order:
            order = AmazonOrder(
                user_id=user_key(),
                amazon_order_id=amazon_order_id,
                marketplace_id=conn.marketplace_id,
            )

        order.order_status = o.get("OrderStatus")

        dt = parse_iso_dt(o.get("PurchaseDate", ""))
        order.purchase_date = to_sp(dt)

        ot = o.get("OrderTotal") or {}
        order.currency = ot.get("CurrencyCode")
        order.order_total_amount = ot.get("Amount")

        order.raw_json = o
        db.session.add(order)
        upserted += 1

    db.session.commit()

    return jsonify(
        {
            "ok": True,
            "from": created_after,
            "orders_upserted": upserted,
            "orders_returned_by_api": len(orders),
        }
    )


@amazon.post("/sync_orders")
@login_required
def sync_orders():
    conn = AmazonConnection.query.filter_by(user_id=user_key()).first()
    if not conn:
        return jsonify({"ok": False, "error": "Integração Amazon não configurada"}), 400

    days = int(request.args.get("days", "30"))
    start = compute_sync_start(conn, days_default=days)
    start_iso = iso_z(start)

    try:
        orders_upserted, items_inserted, returned = _sync_orders_and_items(conn, created_after_iso=start_iso)

        # opcional (recomendado)
        conn.last_sync_at = utcnow()
        db.session.add(conn)

        db.session.commit()
        return jsonify({"ok": True, "from": start_iso, "orders": orders_upserted, "items": items_inserted, "returned": returned})
    except Exception as e:
        db.session.rollback()
        logger.exception("Erro em sync_orders")
        return jsonify({"ok": False, "error": repr(e), "from": start_iso}), 400



@amazon.post("/sync_finances")
@login_required
def sync_finances():
    """
    Sync Finances quota-safe.
    - days: janela curta (default 7)
    - wipe=1: apaga eventos do range e reimporta (idempotente)
    - force_days=1: ignora last_sync_at e usa agora-days
    """
    conn = AmazonConnection.query.filter_by(user_id=user_key()).first()
    if not conn:
        return jsonify({"ok": False, "error": "Integração Amazon não configurada"}), 400

    days = int(request.args.get("days", "7"))
    wipe = request.args.get("wipe", "1") == "1"
    force_days = request.args.get("force_days", "0") == "1"

    # janela segura: se não for force, usa incremental com buffer; se for, usa agora-days
    if force_days:
        start = utcnow() - timedelta(days=days)
    else:
        start = compute_sync_start(conn, days_default=days)

    start_iso = iso_z(start)

    try:
        if wipe:
            # idempotência simples: apaga e reimporta a janela
            AmazonFinancialEvent.query.filter(
                AmazonFinancialEvent.user_id == user_key(),
                AmazonFinancialEvent.posted_date >= start
            ).delete(synchronize_session=False)
            db.session.flush()



        conn.last_sync_at = utcnow()
        db.session.add(conn)

        events_count = _sync_finances(conn, posted_after_iso=start_iso)
        db.session.commit()
        return jsonify({"ok": True, "from": start_iso, "financial_events": events_count, "wipe": wipe})
    except Exception as e:
        db.session.rollback()
        logger.exception("Erro em sync_finances")
        return jsonify({"ok": False, "error": repr(e), "from": start_iso}), 400



@amazon.post("/sync_full")
@login_required
def sync_full():
    """
    Sync completo: Orders+Items + Finances + atualiza last_sync_at.
    """
    conn = AmazonConnection.query.filter_by(user_id=user_key()).first()
    if not conn:
        return jsonify({"ok": False, "error": "Integração Amazon não configurada"}), 400

    now = utcnow()
    days = int(request.args.get("days", "30"))
    start = compute_sync_start(conn, days_default=days)
    start_iso = iso_z(start)

    try:
        orders_count, items_count, returned = _sync_orders_and_items(conn, created_after_iso=start_iso)
        
        # idempotência simples no sync_full também (evita duplicar)
        AmazonFinancialEvent.query.filter(
            AmazonFinancialEvent.user_id == user_key(),
            AmazonFinancialEvent.posted_date >= start
        ).delete(synchronize_session=False)
        db.session.flush()
        
        events_count = _sync_finances(conn, posted_after_iso=start_iso)

        conn.last_sync_at = now
        db.session.add(conn)

        db.session.commit()

        return jsonify(
            {
                "ok": True,
                "from": start_iso,
                "orders": orders_count,
                "items": items_count,
                "returned_orders": returned,
                "financial_events": events_count,
            }
        )
    except Exception as e:
        db.session.rollback()
        logger.exception("Erro em sync_full")
        return jsonify({"ok": False, "error": repr(e), "from": start_iso}), 400


# ---------------------------
# Pages
# ---------------------------
@amazon.get("/orders")
@login_required
def orders_page():
    orders = (
        AmazonOrder.query
        .filter_by(user_id=user_key())
        .order_by(AmazonOrder.purchase_date.desc().nullslast(), AmazonOrder.id.desc())
        .limit(200)
        .all()
    )
    return render_template("amazon/orders.html", orders=orders, SP_TZ=SP_TZ)



# ---------------------------
# DEV endpoints
# ---------------------------
@amazon.post("/dev/mock_finances")
@login_required
def dev_mock_finances():
    if not dev_guard():
        return jsonify({"ok": False, "error": "Endpoint DEV desabilitado"}), 403

    from app.integrations.amazon.mocks.financial_events_mock import financial_events_mock

    amazon_order_id = (request.args.get("order_id") or "").strip()
    if not amazon_order_id:
        return jsonify({"ok": False, "error": "Informe ?order_id=SEU_AMAZON_ORDER_ID"}), 400

    events = financial_events_mock(amazon_order_id)

    inserted = 0
    for event_type, items in events.items():
        if not isinstance(items, list):
            continue

        for ev in items:
            if not isinstance(ev, dict):
                ev = {"value": ev}

            posted_dt = to_sp(parse_iso_dt(ev.get("PostedDate", "")))
            order_id = ev.get("AmazonOrderId") or ev.get("OrderId") or amazon_order_id

            fe = AmazonFinancialEvent(
                user_id=user_key(),
                posted_date=posted_dt,
                event_group_id=ev.get("FinancialEventGroupId"),
                amazon_order_id=order_id,
                event_type=event_type,
                amount=None,
                currency=None,
                raw_json=ev,
            )
            db.session.add(fe)
            inserted += 1

    db.session.commit()
    return jsonify({"ok": True, "inserted": inserted, "amazon_order_id": amazon_order_id})


@amazon.post("/dev/mock_products")
@login_required
def dev_mock_products():
    if not dev_guard():
        return jsonify({"ok": False, "error": "Endpoint DEV desabilitado"}), 403

    payload = request.get_json(silent=True) or {}
    items = payload.get("items") or [
        {"sku": "SKU-TESTE-001", "name": "Produto Teste 001", "cost": 25.00, "price": 89.90, "packaging_cost": 1.00},
        {"sku": "SKU-TESTE-002", "name": "Produto Teste 002", "cost": 12.00, "price": 59.90, "packaging_cost": 0.00},
    ]

    upserted = 0
    for it in items:
        sku = (it.get("sku") or "").strip()
        if not sku:
            continue

        p = Product.query.filter_by(user_id=current_user.id, sku=sku).first()
        if not p:
            p = Product(user_id=current_user.id, sku=sku, name=it.get("name") or sku)

        if it.get("name"):
            p.name = it["name"]
        if it.get("asin"):
            p.asin = it["asin"]
        if it.get("price") is not None:
            p.price = float(it["price"])
        if it.get("cost") is not None:
            p.cost = float(it["cost"])
        if it.get("packaging_cost") is not None and hasattr(p, "packaging_cost"):
            p.packaging_cost = float(it["packaging_cost"])

        db.session.add(p)
        upserted += 1

    db.session.commit()
    return jsonify({"ok": True, "upserted": upserted, "skus": [i.get("sku") for i in items]})


# ---------------------------
# Profit endpoint (finance-event based)
# ---------------------------
@amazon.get("/profit/order/<amazon_order_id>")
@login_required
def profit_order(amazon_order_id: str):
    conn = AmazonConnection.query.filter_by(user_id=user_key()).first()
    if not conn:
        return jsonify({"ok": False, "error": "Integração Amazon não configurada"}), 400

    def r2(x):
        try:
            return round(float(x), 2)
        except Exception:
            return 0.0

    fin_rows = AmazonFinancialEvent.query.filter_by(user_id=user_key(), amazon_order_id=amazon_order_id).all()
    shipment_events = [r.raw_json for r in fin_rows if r.event_type == "ShipmentEventList"]

    if not shipment_events:
        # tenta um sync curto e focado (quota-safe) baseado na data do pedido
        order = AmazonOrder.query.filter_by(user_id=user_key(), amazon_order_id=amazon_order_id).first()

        start = utcnow() - timedelta(days=7)
        if order and order.purchase_date:
            purchase_utc = order.purchase_date.astimezone(timezone.utc)
            start = purchase_utc - timedelta(days=5)

        start_iso = iso_z(start)

        try:
            AmazonFinancialEvent.query.filter(
                AmazonFinancialEvent.user_id == user_key(),
                AmazonFinancialEvent.posted_date >= start
            ).delete(synchronize_session=False)
            db.session.flush()

            _ = _sync_finances(conn=conn, posted_after_iso=start_iso)
            db.session.commit()

            fin_rows = AmazonFinancialEvent.query.filter_by(user_id=user_key(), amazon_order_id=amazon_order_id).all()
            shipment_events = [r.raw_json for r in fin_rows if r.event_type == "ShipmentEventList"]

        except Exception as e:
            db.session.rollback()
            return jsonify({
                "ok": False,
                "amazon_order_id": amazon_order_id,
                "mode": "no_finance_events",
                "message": "Não encontrei ShipmentEventList e falhou ao tentar sync_finances curto.",
                "error": repr(e),
                "from": start_iso,
            }), 400

        if not shipment_events:
            return jsonify({
                "ok": True,
                "amazon_order_id": amazon_order_id,
                "mode": "no_finance_events",
                "message": "Nenhum ShipmentEventList encontrado para este pedido mesmo após sync curto. Tente ampliar a janela: POST /sync_finances?days=30&wipe=1",
                "from": start_iso,
            })



    from app.services.profit_calc import extract_net_from_shipment_events
    net_info = extract_net_from_shipment_events(shipment_events)

    imposto_rate_pct = float(getattr(current_user, "default_tax_rate", 4.0) or 0.0)
    imposto_rate = imposto_rate_pct / 100.0

    amazon_revenue = r2(net_info["revenue"])
    amazon_fees = r2(net_info["fees"])
    amazon_net = r2(net_info["net"])

    # imposto sobre faturamento
    imposto = r2(amazon_revenue * imposto_rate)

    cmv_total = 0.0
    embalagem_total = 0.0

    total_revenue_for_split = 0.0
    for sku, v in net_info["by_sku"].items():
        total_revenue_for_split += float(v.get("revenue", 0))

    by_sku = {}
    for sku, v in net_info["by_sku"].items():
        sku_revenue = r2(v["revenue"])
        sku_fees = r2(v["fees"])
        sku_net = r2(v["net"])
        sku_qty = float(v.get("qty", 0))

        link = AmazonSkuLink.query.filter_by(user_id=user_key(), amazon_seller_sku=sku).first()
        if link and link.product:
            prod = link.product
        else:
            # fallback: tenta casar direto pelo sku igual
            prod = Product.query.filter_by(user_id=current_user.id, sku=sku).first()
        unit_cost = float(prod.cost) if prod else 0.0
        unit_pack = float(getattr(prod, "packaging_cost", 0.0)) if (prod and hasattr(prod, "packaging_cost")) else 0.0

        sku_cmv = unit_cost * sku_qty
        sku_pack = unit_pack * sku_qty
        cmv_total += sku_cmv
        embalagem_total += sku_pack

        tax_alloc = imposto * (sku_revenue / total_revenue_for_split) if total_revenue_for_split > 0 else 0.0
        tax_alloc = r2(tax_alloc)

        sku_net_after_tax = r2(sku_net - tax_alloc)
        sku_profit_after_tax = r2(sku_net_after_tax - sku_cmv - sku_pack)

        by_sku[sku] = {
            "qty": r2(sku_qty),
            "revenue": sku_revenue,
            "fees": sku_fees,
            "net": sku_net,
            "tax_allocated": tax_alloc,
            "net_after_tax": sku_net_after_tax,
            "unit_cost": r2(unit_cost),
            "cmv": r2(sku_cmv),
            "unit_packaging_cost": r2(unit_pack),
            "embalagem": r2(sku_pack),
            "profit_after_tax": sku_profit_after_tax,
        }

    cmv_total = r2(cmv_total)
    embalagem_total = r2(embalagem_total)

    lucro = r2(amazon_net - (cmv_total + embalagem_total + imposto))

    return jsonify({
        "ok": True,
        "amazon_order_id": amazon_order_id,
        "mode": "real_from_finance_events",
        "amazon_revenue": amazon_revenue,
        "amazon_fees": amazon_fees,
        "amazon_net": amazon_net,
        "imposto_rate_pct": r2(imposto_rate_pct),
        "imposto": imposto,
        "tax_base": "amazon_revenue",
        "cmv_total": cmv_total,
        "embalagem_total": embalagem_total,
        "lucro": lucro,
        "by_sku": by_sku,
        "notes": {
            "tax_source": "User.default_tax_rate (%)",
            "tax_allocation": "Proporcional ao revenue por SKU",
            "cmv_source": "Product.cost by SKU",
            "embalagem_source": "Product.packaging_cost by SKU",
        }
    })

@amazon.get("/sync_full_debug")
@login_required
def sync_full_debug():
    # chama o POST real por dentro
    return sync_full()


@amazon.post("/sync_items_batch")
@login_required
def sync_items_batch():
    conn = AmazonConnection.query.filter_by(user_id=user_key()).first()
    if not conn:
        return jsonify({"ok": False, "error": "Integração Amazon não configurada"}), 400

    limit = int(request.args.get("limit", "15"))

    orders = (AmazonOrder.query
              .filter_by(user_id=user_key())
              .order_by(AmazonOrder.purchase_date.desc().nullslast(), AmazonOrder.id.desc())
              .limit(200)
              .all())

    processed = 0
    inserted_items = 0
    skipped = 0

    for o in orders:
        if processed >= limit:
            break

        exists = AmazonOrderItem.query.filter_by(user_id=user_key(), amazon_order_id=o.amazon_order_id).first()
        if exists:
            skipped += 1
            continue

        try:
            items = list_order_items(conn, o.amazon_order_id)
        except Exception as e:
            return jsonify({"ok": False, "error": f"Falha ao buscar itens {o.amazon_order_id}: {repr(e)}"}), 400

        for it in items:
            ip = it.get("ItemPrice") or {}
            item = AmazonOrderItem(
                user_id=user_key(),
                amazon_order_id=o.amazon_order_id,
                seller_sku=it.get("SellerSKU"),
                asin=it.get("ASIN"),
                quantity=it.get("QuantityOrdered"),
                item_price=ip.get("Amount"),
                currency=ip.get("CurrencyCode"),
                raw_json=it,
            )
            db.session.add(item)
            inserted_items += 1

        processed += 1

    db.session.commit()
    return jsonify({"ok": True, "processed_orders": processed, "skipped_orders": skipped, "inserted_items": inserted_items})


@amazon.get("/orders/<amazon_order_id>/details")
@login_required
def order_details(amazon_order_id: str):
    # pedido (para status + total)
    order = AmazonOrder.query.filter_by(user_id=user_key(), amazon_order_id=amazon_order_id).first()
    order_status = order.order_status if order else None
    order_total = float(order.order_total_amount or 0) if order else 0.0
    order_currency = order.currency if order else None

    # itens do pedido
    items = (AmazonOrderItem.query
             .filter_by(user_id=user_key(), amazon_order_id=amazon_order_id)
             .all())

    # financeiros (se tiver)
    fin_rows = (AmazonFinancialEvent.query
                .filter_by(user_id=user_key(), amazon_order_id=amazon_order_id)
                .all())
    shipment_events = [r.raw_json for r in fin_rows if r.event_type == "ShipmentEventList"]

    by_sku_fin = {}
    if shipment_events:
        from app.services.profit_calc import extract_net_from_shipment_events
        net_info = extract_net_from_shipment_events(shipment_events)
        for sku, v in net_info["by_sku"].items():
            by_sku_fin[sku] = {
                "revenue": round(float(v["revenue"]), 2),
                "fees": round(float(v["fees"]), 2),
                "net": round(float(v["net"]), 2),
                "qty": float(v["qty"]),
            }

    # imposto configurado (percentual)
    imposto_rate_pct = float(getattr(current_user, "default_tax_rate", 0.0) or 0.0)  # ex: 6.0
    imposto_rate = imposto_rate_pct / 100.0

    # helper: tenta extrair amount de dicts (ex: {"CurrencyCode":"BRL","Amount":"10.00"})
    def _amount_from_money(m):
        try:
            if isinstance(m, dict):
                return float(m.get("Amount") or m.get("CurrencyAmount") or 0)
        except Exception:
            pass
        return 0.0

    result_items = []
    for it in items:
        sku = it.seller_sku or ""
        qty = float(it.quantity or 0)

        # 1) preço do modelo (coluna item_price)
        price = float(it.item_price or 0)

        # 2) tenta extrair do raw_json (alguns retornam ItemPrice/PromotionDiscount etc)
        raw = it.raw_json or {}
        if price == 0 and isinstance(raw.get("ItemPrice"), dict):
            price = _amount_from_money(raw["ItemPrice"])

        # 3) se ainda 0 e o pedido tem total, rateia por nº de itens
        if price == 0 and order_total > 0 and len(items) > 0:
            price = round(order_total / len(items), 2)

        link = AmazonSkuLink.query.filter_by(user_id=user_key(), amazon_seller_sku=sku).first()
        if link and link.product:
            prod = link.product
        else:
            # fallback: tenta casar direto pelo sku igual
            prod = Product.query.filter_by(user_id=current_user.id, sku=sku).first()
        unit_cost = float(prod.cost) if prod else 0.0
        unit_pack = float(getattr(prod, "packaging_cost", 0.0)) if prod else 0.0

        cmv = round(unit_cost * qty, 2)
        embalagem = round(unit_pack * qty, 2)

        fin = by_sku_fin.get(sku)
        if fin:
            revenue = fin["revenue"]
            fees = fin["fees"]
            net = fin["net"]
        else:
            # fallback estimado: usa o price como revenue
            revenue = round(price, 2)
            fees = 0.0
            net = round(revenue + fees, 2)

        imposto = round(revenue * imposto_rate, 2)
        lucro = round(net - imposto - cmv - embalagem, 2)
        margem = round((lucro / revenue) * 100, 2) if revenue > 0 else 0.0

        result_items.append({
            "sku": sku,
            "asin": it.asin,
            "qty": qty,
            "price": round(price, 2),
            "revenue": revenue,
            "fees": fees,
            "net": net,
            "imposto": imposto,
            "cmv": cmv,
            "embalagem": embalagem,
            "lucro": lucro,
            "margem_pct": margem,
        })

    return jsonify({
        "ok": True,
        "amazon_order_id": amazon_order_id,
        "order_status": order_status,
        "order_total": round(order_total, 2),
        "order_currency": order_currency,
        "items_count": len(result_items),
        "imposto_rate_pct": round(imposto_rate_pct, 2),
        "items": result_items,
        "has_finance_events": bool(shipment_events),
        "has_items": bool(items),
    })

@amazon.get("/sku_links")
@login_required
def sku_links_page():
    products_rows = (
        Product.query
        .filter_by(user_id=current_user.id)
        .order_by(Product.sku.asc())
        .all()
    )
    products = [{"id": int(p.id), "sku": p.sku, "name": p.name or p.sku} for p in products_rows]

    links = (
        AmazonSkuLink.query
        .filter_by(user_id=user_key())
        .order_by(AmazonSkuLink.amazon_seller_sku.asc())
        .all()
    )

    inv_rows = AmazonInventorySnapshot.query.filter_by(user_id=user_key()).all()
    inventory_map = {r.seller_sku: int(r.fulfillable_qty or 0) for r in inv_rows}

    return render_template("amazon/sku_links.html", products=products, links=links, inventory_map=inventory_map)

@amazon.get("/sku_links/missing")
@login_required
def sku_links_missing():
    # pega SKUs e o último ASIN conhecido daquele SKU a partir de amazon_order_items
    rows = db.session.execute(
        db.text("""
        with skus as (
          select
            seller_sku,
            count(*) as cnt,
            max(id) as last_id
          from public.amazon_order_items
          where user_id = :uid
            and coalesce(seller_sku,'') <> ''
          group by seller_sku
        )
        select
          s.seller_sku,
          s.cnt,
          i.asin
        from skus s
        left join public.amazon_order_items i
          on i.id = s.last_id
        order by s.cnt desc
        """),
        {"uid": user_key()}
    ).fetchall()

    linked = set(r[0] for r in db.session.execute(
        db.text("""
        select amazon_seller_sku
        from public.amazon_sku_links
        where user_id = :uid
        """),
        {"uid": user_key()}
    ).fetchall())

    missing = []
    for seller_sku, cnt, asin in rows:
        if seller_sku not in linked:
            missing.append({
                "seller_sku": seller_sku,
                "count": int(cnt),
                "asin": asin
            })

    return jsonify({"ok": True, "missing": missing, "missing_count": len(missing)})


@amazon.post("/sku_links")
@login_required
def sku_links_upsert():
    data = request.get_json(force=True) or {}
    seller_sku = (data.get("amazon_seller_sku") or "").strip()
    product_id = data.get("product_id")

    if not seller_sku or not product_id:
        return jsonify({"ok": False, "error": "Informe amazon_seller_sku e product_id"}), 400

    link = AmazonSkuLink.query.filter_by(user_id=user_key(), amazon_seller_sku=seller_sku).first()
    if not link:
        link = AmazonSkuLink(user_id=user_key(), amazon_seller_sku=seller_sku)

    link.product_id = int(product_id)
    link.marketplace_id = data.get("marketplace_id") or None
    link.asin = data.get("asin") or None

    # ✅ (Opcional recomendado) Preenche o ASIN no Product automaticamente
    if link.asin:
        prod = Product.query.filter_by(id=link.product_id, user_id=current_user.id).first()
        if prod and not prod.asin:
            prod.asin = link.asin
            db.session.add(prod)



    db.session.add(link)
    db.session.commit()

    return jsonify({"ok": True, "id": link.id})

@amazon.route("/sku_links/<int:link_id>/delete", methods=["POST", "DELETE"])
@login_required
def sku_links_delete(link_id: int):
    link = AmazonSkuLink.query.filter_by(id=link_id, user_id=user_key()).first()
    if not link:
        return jsonify({"ok": False, "error": "Vínculo não encontrado"}), 404

    db.session.delete(link)
    db.session.commit()
    return jsonify({"ok": True})

from app.models.amazon_inventory import AmazonInventorySnapshot
from app.integrations.amazon.service import get_inventory_summaries

@amazon.post("/sync_inventory")
@login_required
def sync_inventory():
    conn = AmazonConnection.query.filter_by(user_id=user_key()).first()
    if not conn:
        return jsonify({"ok": False, "error": "Integração Amazon não configurada"}), 400

    marketplace_id = conn.marketplace_id

    try:
        summaries = get_inventory_summaries(conn, marketplace_id)
    except Exception as e:
        return jsonify({"ok": False, "error": repr(e)}), 400

    # upsert por (user_id, seller_sku)
    inserted = 0
    updated = 0

    for s in summaries:
        # nomes comuns
        seller_sku = s.get("sellerSku") or s.get("SellerSku") or s.get("sellerSKU") or s.get("SellerSKU")
        asin = s.get("asin") or s.get("ASIN")

        if not seller_sku:
            continue

        total_qty = s.get("totalQuantity") or s.get("TotalQuantity") or 0
        details = s.get("inventoryDetails") or s.get("InventoryDetails") or {}

        reserved = details.get("reservedQuantity") or details.get("ReservedQuantity") or 0
        inbound_working = details.get("inboundWorkingQuantity") or details.get("InboundWorkingQuantity") or 0
        inbound_shipped = details.get("inboundShippedQuantity") or details.get("InboundShippedQuantity") or 0
        inbound_receiving = details.get("inboundReceivingQuantity") or details.get("InboundReceivingQuantity") or 0

        row = AmazonInventorySnapshot.query.filter_by(
            user_id=user_key(),
            seller_sku=seller_sku
        ).first()

        if not row:
            row = AmazonInventorySnapshot(
                user_id=user_key(),
                marketplace_id=marketplace_id,
                seller_sku=seller_sku
            )
            inserted += 1
        else:
            updated += 1

        row.asin = asin
        row.fulfillable_qty = int(total_qty or 0)
        row.reserved_qty = int(reserved or 0)
        row.inbound_working_qty = int(inbound_working or 0)
        row.inbound_shipped_qty = int(inbound_shipped or 0)
        row.inbound_receiving_qty = int(inbound_receiving or 0)

        db.session.add(row)

    db.session.commit()
    return jsonify({"ok": True, "inserted": inserted, "updated": updated, "total": len(summaries)})
