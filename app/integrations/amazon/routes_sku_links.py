import logging

from flask import request, jsonify, render_template
from flask_login import login_required, current_user

from app import db
from app.models.product import Product
from app.models.amazon_sku_link import AmazonSkuLink
from app.models.amazon_inventory import AmazonInventorySnapshot
from app.integrations.amazon import amazon
from app.integrations.amazon.utils import user_key

logger = logging.getLogger(__name__)


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

    return render_template(
        "amazon/sku_links.html",
        products=products,
        links=links,
        inventory_map=inventory_map,
    )


@amazon.get("/sku_links/missing")
@login_required
def sku_links_missing():
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
        {"uid": user_key()},
    ).fetchall()

    linked = set(
        r[0] for r in db.session.execute(
            db.text("""
            select amazon_seller_sku
            from public.amazon_sku_links
            where user_id = :uid
            """),
            {"uid": user_key()},
        ).fetchall()
    )

    missing = [
        {"seller_sku": seller_sku, "count": int(cnt), "asin": asin}
        for seller_sku, cnt, asin in rows
        if seller_sku not in linked
    ]

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
