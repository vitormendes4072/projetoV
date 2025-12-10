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
    products = current_user.products.all()
    return render_template('produtos/lista.html', products=products)

@produtos_bp.route('/produtos/novo', methods=['GET', 'POST'])
@login_required
def criar_produto():
    form = ProductForm()
    if form.validate_on_submit():
        produto = Product(
            name=form.name.data,
            sku=form.sku.data,
            asin=form.asin.data,
            price=form.price.data,
            cost=form.cost.data,
            stock_quantity=form.stock_quantity.data,
            image_url=form.image_url.data,
            owner=current_user
        )
        db.session.add(produto)
        db.session.commit() # Comita primeiro para gerar o ID do produto
        
        # Registra o histórico de Criação
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
        # Atualiza os dados
        product.name = form.name.data
        product.sku = form.sku.data
        product.asin = form.asin.data
        product.price = form.price.data
        product.cost = form.cost.data
        product.stock_quantity = form.stock_quantity.data
        product.image_url = form.image_url.data
        
        # Registra o histórico de Edição (com os novos valores)
        registrar_historico(product, current_user, 'Alteração Manual')
        
        db.session.commit()
        flash('Produto atualizado com sucesso!', 'success')
        return redirect(url_for('produtos.lista_produtos'))
    
    elif request.method == 'GET':
        form.name.data = product.name
        form.sku.data = product.sku
        form.asin.data = product.asin
        form.price.data = product.price
        form.cost.data = product.cost
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
        
    # Busca o histórico ordenado do mais recente para o mais antigo
    historico = product.history.order_by(ProductHistory.changed_at.desc()).all()
    
    return render_template('produtos/historico.html', product=product, historico=historico)