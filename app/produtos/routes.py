# app/produtos/routes.py
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from app import db
from app.models.product import Product, ProductHistory # <--- Importe o History
from .forms import ProductForm

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

@produtos_bp.route('/produtos', methods=['GET'])
@login_required
def lista_produtos():
    page = request.args.get('page', 1, type=int)
    products = current_user.products.order_by(Product.name).paginate(page=page, per_page=20, error_out=False)
    return render_template('produtos/lista.html', products=products)

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