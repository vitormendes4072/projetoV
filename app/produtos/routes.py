# app/produtos/routes.py
import csv
import io
import logging
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, send_from_directory, current_app
from flask_login import login_required, current_user
from app import db
from app.models.product import Product, ProductHistory
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

    skus_existentes = {
        p.sku for p in current_user.products.with_entities(Product.sku).all()
    }

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
    products = current_user.products.order_by(Product.name).paginate(page=page, per_page=20, error_out=False)
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
            packaging_cost=form.packaging_cost.data or 0.0,  # ✅ OK
            stock_quantity=form.stock_quantity.data,
            image_url=form.image_url.data,
            owner=current_user
        )
        db.session.add(produto)
        db.session.commit()  # gera ID

        registrar_historico(produto, current_user, 'Criação Inicial')
        db.session.commit()

        flash('Produto criado com sucesso!', 'success')
        return redirect(url_for('produtos.lista_produtos'))

    return render_template('produtos/editar.html', form=form, title="Novo Produto")


@produtos_bp.route('/produtos/editar/<int:product_id>', methods=['GET', 'POST'])
@login_required
def editar_produto(product_id):
    product = Product.query.get_or_404(product_id)
    if product.owner != current_user:
        abort(403)

    form = ProductForm(original_sku=product.sku)

    if form.validate_on_submit():
        product.name = form.name.data
        product.sku = form.sku.data
        product.price = form.price.data or 0.0
        product.cost = form.cost.data
        product.packaging_cost = form.packaging_cost.data or 0.0  # ✅ OK
        product.stock_quantity = form.stock_quantity.data
        product.image_url = form.image_url.data

        registrar_historico(product, current_user, 'Alteração Manual')

        db.session.commit()
        flash('Produto atualizado com sucesso!', 'success')
        return redirect(url_for('produtos.lista_produtos'))

    elif request.method == 'GET':
        form.name.data = product.name
        form.sku.data = product.sku
        form.price.data = product.price
        form.cost.data = product.cost
        form.packaging_cost.data = product.packaging_cost  # ✅ FALTAVA ISSO
        form.stock_quantity.data = product.stock_quantity
        form.image_url.data = product.image_url

    return render_template('produtos/editar.html', form=form, title="Editar Produto")


# --- NOVA ROTA: VISUALIZAR HISTÓRICO ---
@produtos_bp.route('/produtos/historico/<int:product_id>')
@login_required
def historico_produto(product_id):
    product = Product.query.get_or_404(product_id)
    if product.owner != current_user:
        abort(403)
        
    page = request.args.get('page', 1, type=int)
    historico = product.history.order_by(ProductHistory.changed_at.desc()).paginate(page=page, per_page=10, error_out=False)

    return render_template('produtos/historico.html', product=product, historico=historico)