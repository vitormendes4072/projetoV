# app/produtos/routes.py
import csv
import io
import logging
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, send_from_directory, current_app, Response, jsonify
from flask import stream_with_context
from flask_login import login_required, current_user
from app import db
from app.models.product import Product, ProductHistory
from app.services.comparativo import get_sku_comparison
from .forms import ProductForm, CsvUploadForm

logger = logging.getLogger(__name__)

produtos_bp = Blueprint('produtos', __name__)

# Função Auxiliar para registrar histórico
def registrar_historico(produto, user, acao):
    historico = ProductHistory(
        product_id=produto.id,
        price=produto.price,
        cost=produto.cost,
        stock_quantity=produto.stock_quantity,
        action_type=acao,
        user_id=user.id
    )
    db.session.add(historico)

COLUNAS_OBRIGATORIAS = {'name', 'sku', 'cost'}
LIMITE_LINHAS = 1000
_CSV_CHUNK = 500


def _iter_produtos_csv(uid: int):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(['name', 'sku', 'asin', 'cost', 'price', 'packaging_cost', 'stock_quantity', 'created_at'])
    yield buf.getvalue()
    buf.seek(0)
    buf.truncate()

    offset = 0
    while True:
        batch = db.session.scalars(
            db.select(Product)
            .where(Product.user_id == uid)
            .order_by(Product.name)
            .limit(_CSV_CHUNK)
            .offset(offset)
        ).all()
        if not batch:
            break
        for p in batch:
            writer.writerow([
                p.name, p.sku, p.asin or '',
                p.cost, p.price, p.packaging_cost,
                p.stock_quantity,
                p.created_at.strftime('%Y-%m-%d') if p.created_at else '',
            ])
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate()
        offset += _CSV_CHUNK


@produtos_bp.route('/produtos/exportar-csv')
@login_required
def exportar_csv():
    return Response(
        stream_with_context(_iter_produtos_csv(current_user.id)),
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': 'attachment; filename="produtos.csv"'},
    )


@produtos_bp.route('/produtos/importar-csv', methods=['POST'])
@login_required
def importar_csv():
    form = CsvUploadForm()
    if not form.validate_on_submit():
        flash('Arquivo inválido. Envie um arquivo .csv.', 'danger')
        return redirect(url_for('produtos.lista_produtos'))

    conteudo = form.arquivo.data.read().decode('utf-8-sig')
    # detecta separador
    separador = ';' if conteudo.count(';') > conteudo.count(',') else ','
    reader = csv.DictReader(io.StringIO(conteudo), delimiter=separador)

    if not reader.fieldnames or not COLUNAS_OBRIGATORIAS.issubset(
        {c.strip().lower() for c in reader.fieldnames}
    ):
        flash('CSV inválido: colunas obrigatórias ausentes (name, sku, cost).', 'danger')
        return redirect(url_for('produtos.lista_produtos'))

    skus_existentes = set(
        db.session.scalars(db.select(Product.sku).where(Product.user_id == current_user.id)).all()
    )

    importados, ignorados = 0, []

    for i, row in enumerate(reader, start=2):
        if i > LIMITE_LINHAS + 1:
            flash(f'Limite de {LIMITE_LINHAS} linhas atingido. Divida o arquivo.', 'warning')
            break

        row = {k.strip().lower(): v.strip() for k, v in row.items() if k}

        sku = row.get('sku', '')
        name = row.get('name', '')

        if not sku or not name:
            ignorados.append(f'linha {i} (sku/name vazio)')
            continue

        if sku in skus_existentes:
            ignorados.append(sku)
            continue

        try:
            produto = Product(
                name=name,
                sku=sku,
                price=float(row.get('price') or 0),
                cost=float(row.get('cost', 0)),
                packaging_cost=float(row.get('packaging_cost') or 0),
                stock_quantity=int(float(row.get('stock_quantity') or 0)),
                image_url=row.get('image_url') or None,
                owner=current_user,
            )
            db.session.add(produto)
            db.session.flush()  # gera ID sem commit
            db.session.add(ProductHistory(
                product_id=produto.id,
                price=produto.price,
                cost=produto.cost,
                stock_quantity=produto.stock_quantity,
                action_type='Importação CSV',
                user_id=current_user.id,
            ))
            skus_existentes.add(sku)
            importados += 1
        except (ValueError, KeyError) as e:
            logger.warning("Erro ao importar linha %d: %s", i, e)
            ignorados.append(f'linha {i} (valor inválido)')

    db.session.commit()

    msg = f'{importados} produto(s) importado(s).'
    if ignorados:
        msg += f' {len(ignorados)} ignorado(s): {", ".join(ignorados[:10])}'
        if len(ignorados) > 10:
            msg += f' e mais {len(ignorados) - 10}.'
    flash(msg, 'success' if importados else 'warning')
    return redirect(url_for('produtos.lista_produtos'))


@produtos_bp.route('/produtos', methods=['GET'])
@login_required
def lista_produtos():
    page = request.args.get('page', 1, type=int)
    products = db.paginate(db.select(Product).where(Product.user_id == current_user.id).order_by(Product.name), page=page, per_page=20, error_out=False)
    csv_form = CsvUploadForm()
    return render_template('produtos/lista.html', products=products, csv_form=csv_form)

@produtos_bp.route('/produtos/novo', methods=['GET', 'POST'])
@login_required
def criar_produto():
    form = ProductForm()
    if form.validate_on_submit():
        produto = Product(
            name=form.name.data,
            sku=form.sku.data,
            price=form.price.data or 0.0,
            cost=form.cost.data,
            packaging_cost=form.packaging_cost.data or 0.0,
            stock_quantity=form.stock_quantity.data,
            min_stock=form.min_stock.data if form.min_stock.data is not None else 5,
            image_url=form.image_url.data,
            margin_alert_threshold=form.margin_alert_threshold.data,
            owner=current_user
        )
        db.session.add(produto)
        db.session.commit()  # gera ID

        registrar_historico(produto, current_user, 'Criação Inicial')
        db.session.commit()

        flash('Produto criado com sucesso!', 'success')
        return redirect(url_for('produtos.lista_produtos'))

    return render_template('produtos/editar.html', form=form, title="Novo Produto", product=None)


@produtos_bp.route('/produtos/editar/<int:product_id>', methods=['GET', 'POST'])
@login_required
def editar_produto(product_id):
    product = db.get_or_404(Product, product_id)
    if product.owner != current_user:
        abort(403)

    form = ProductForm(original_sku=product.sku)

    if form.validate_on_submit():
        product.name = form.name.data
        product.sku = form.sku.data
        product.price = form.price.data or 0.0
        product.cost = form.cost.data
        product.packaging_cost = form.packaging_cost.data or 0.0
        product.stock_quantity = form.stock_quantity.data
        product.min_stock = form.min_stock.data if form.min_stock.data is not None else 5
        product.image_url = form.image_url.data
        product.margin_alert_threshold = form.margin_alert_threshold.data

        registrar_historico(product, current_user, 'Alteração Manual')

        db.session.commit()
        flash('Produto atualizado com sucesso!', 'success')
        return redirect(url_for('produtos.lista_produtos'))

    elif request.method == 'GET':
        form.name.data = product.name
        form.sku.data = product.sku
        form.price.data = product.price
        form.cost.data = product.cost
        form.packaging_cost.data = product.packaging_cost
        form.stock_quantity.data = product.stock_quantity
        form.min_stock.data = product.min_stock
        form.image_url.data = product.image_url
        form.margin_alert_threshold.data = (
            float(product.margin_alert_threshold)
            if product.margin_alert_threshold is not None
            else None
        )

    return render_template('produtos/editar.html', form=form, title="Editar Produto", product=product)


@produtos_bp.route('/produtos/<int:product_id>/ajustar-estoque', methods=['POST'])
@login_required
def ajustar_estoque(product_id):
    product = db.get_or_404(Product, product_id)
    if product.owner != current_user:
        abort(403)
    try:
        delta = int(request.form.get('delta', 0))
    except (ValueError, TypeError):
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({"ok": False, "error": "Valor de ajuste inválido."}), 400
        flash('Valor de ajuste inválido.', 'danger')
        return redirect(url_for('produtos.editar_produto', product_id=product_id))
    if delta == 0:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({"ok": False, "error": "Informe uma variação diferente de zero."}), 400
        flash('Informe uma variação diferente de zero.', 'warning')
        return redirect(url_for('produtos.editar_produto', product_id=product_id))
    motivo = request.form.get('motivo', '').strip() or 'Ajuste Manual'
    product.stock_quantity = (product.stock_quantity or 0) + delta
    registrar_historico(product, current_user, f'Ajuste de Estoque: {motivo}')
    db.session.commit()
    sinal = '+' if delta >= 0 else ''
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            "ok": True,
            "new_qty": product.stock_quantity,
            "message": f'Estoque ajustado em {sinal}{delta} un. Novo total: {product.stock_quantity}.',
        })
    flash(f'Estoque ajustado em {sinal}{delta} un. Novo total: {product.stock_quantity}.', 'success')
    return redirect(url_for('produtos.editar_produto', product_id=product_id))


# Whitelist de campos editáveis via PATCH inline
_PATCH_FIELDS: dict[str, type] = {
    "price": float,
    "cost": float,
    "packaging_cost": float,
    "min_stock": int,
    "stock_quantity": int,
}


@produtos_bp.route('/produtos/<int:product_id>', methods=['PATCH'])
@login_required
def patch_produto(product_id):
    """Edição inline AJAX de um campo numérico do produto.

    Body JSON: {"field": "price", "value": 39.90}
    Retorna: {"ok": true, "field": "price", "new_value": 39.9}
    """
    product = db.get_or_404(Product, product_id)
    if product.owner != current_user:
        return jsonify({"ok": False, "error": "Acesso negado."}), 403

    data = request.get_json(silent=True) or {}
    field = data.get("field", "")
    raw_value = data.get("value")

    if field not in _PATCH_FIELDS:
        return jsonify({"ok": False, "error": f"Campo '{field}' não permitido."}), 400

    try:
        cast = _PATCH_FIELDS[field]
        value = cast(raw_value)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Valor inválido."}), 400

    if cast is float and value < 0:
        return jsonify({"ok": False, "error": "Valor não pode ser negativo."}), 400

    setattr(product, field, value)
    registrar_historico(product, current_user, f'Edição inline: {field}')
    db.session.commit()
    return jsonify({"ok": True, "field": field, "new_value": getattr(product, field)})


# --- NOVA ROTA: VISUALIZAR HISTÓRICO ---
@produtos_bp.route('/produtos/historico/<int:product_id>')
@login_required
def historico_produto(product_id):
    product = db.get_or_404(Product, product_id)
    if product.owner != current_user:
        abort(403)

    page = request.args.get('page', 1, type=int)
    historico = db.paginate(
        db.select(ProductHistory).where(ProductHistory.product_id == product.id).order_by(ProductHistory.changed_at.desc()),
        page=page, per_page=10, error_out=False,
    )

    serie = db.session.scalars(
        db.select(ProductHistory).where(ProductHistory.product_id == product.id).order_by(ProductHistory.changed_at.asc()).limit(200)
    ).all()

    # compute stock delta per entry (vs chronologically previous entry)
    deltas: dict[int, int | None] = {}
    prev_stock = None
    for entry in serie:
        deltas[entry.id] = None if prev_stock is None else entry.stock_quantity - prev_stock
        prev_stock = entry.stock_quantity

    grafico = {
        "labels": [e.changed_at.strftime('%d/%m %H:%M') for e in serie],
        "precos": [float(e.price) for e in serie],
        "custos": [float(e.cost) for e in serie],
        "estoques": [e.stock_quantity for e in serie],
    }

    return render_template('produtos/historico.html', product=product, historico=historico, grafico=grafico, deltas=deltas)


# --- COMPARATIVO: MARGEM ESTIMADA x REAL ---
@produtos_bp.route('/produtos/<int:product_id>/comparativo')
@login_required
def comparativo_produto(product_id):
    product = db.get_or_404(Product, product_id)
    if product.owner != current_user:
        abort(403)

    tax_rate = float(getattr(current_user, 'default_tax_rate', 0.0) or 0.0)
    data = get_sku_comparison(current_user.id, product, tax_rate)
    return render_template('produtos/comparativo.html', tax_rate=tax_rate, **data)
