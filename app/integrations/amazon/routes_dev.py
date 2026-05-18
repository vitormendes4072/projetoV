import logging

from flask import request, jsonify
from flask_login import login_required, current_user

from app import db
from app.models.product import Product
from app.models.amazon_finances import AmazonFinancialEvent
from app.integrations.amazon import amazon
from app.integrations.amazon.utils import user_key, parse_iso_dt, to_sp, dev_guard

logger = logging.getLogger(__name__)


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
