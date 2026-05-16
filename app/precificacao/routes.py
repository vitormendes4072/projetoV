# app/precificacao/routes.py
from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from app import db
from app.models.pricing import PricingHistory
from app.services.pricing import calcular_fba
from .forms import CalculatorForm

pricing = Blueprint('pricing', __name__)

@pricing.route('/calculator', methods=['GET', 'POST'])
@login_required
def calculator():
    form = CalculatorForm()
    results = None
    
    # Mensagem de alerta para MEI
    is_mei = False
    if current_user.tax_regime == 'mei':
        is_mei = True

    # --- AUTO-PREENCHIMENTO INTELIGENTE (GET) ---
    if request.method == 'GET':
        # 1. Pega parâmetros da URL (vindo da lista de produtos)
        price_arg = request.args.get('price')
        cost_arg = request.args.get('cost')
        
        if price_arg:
            try: form.price.data = float(price_arg)
            except ValueError: pass
        
        if cost_arg:
            try: form.cost.data = float(cost_arg)
            except ValueError: pass
        
        # 2. Aplica Regra Fiscal
        if is_mei:
            # REGRA MEI: Imposto sobre venda é ZERO (paga-se DAS fixo mensal)
            form.tax_rate.data = 0.0
            # Pode-se deixar o campo readonly no template ou apenas avisar
        elif current_user.default_tax_rate is not None:
            # Outros regimes: Usa a taxa configurada
            form.tax_rate.data = current_user.default_tax_rate
    
    # --- CÁLCULO (POST) ---
    if form.validate_on_submit():
        price = form.price.data
        cost = form.cost.data
        fba_fee = form.fba_fee.data
        referral_pct = form.referral_fee.data
        tax_pct = form.tax_rate.data
        marketing = form.marketing.data or 0
        
        # Validação extra de segurança para MEI no POST
        if is_mei and tax_pct > 0:
            flash('Atenção: MEI geralmente possui alíquota zero sobre venda unitária (DAS é fixo).', 'warning')
        
        results = calcular_fba(price, cost, fba_fee, referral_pct, tax_pct, marketing)

        if form.save.data:
            historico = PricingHistory(
                user_id=current_user.id,
                title=form.title.data or f"Simulação R$ {price:.2f}",
                price=price,
                cost=cost,
                fba_fee=fba_fee,
                referral_fee=referral_pct,
                tax_rate=tax_pct,
                marketing=marketing,
                net_profit=results["net_profit"],
                margin=results["margin"],
                roi=results["roi"],
            )
            db.session.add(historico)
            db.session.commit()
            flash('Simulação salva no histórico!', 'success')
            return redirect(url_for('pricing.calculator'))

    page = request.args.get('page', 1, type=int)
    history_items = PricingHistory.query.filter_by(user_id=current_user.id).order_by(PricingHistory.created_at.desc()).paginate(page=page, per_page=10, error_out=False)

    return render_template('calculator.html', form=form, results=results, history=history_items, is_mei=is_mei)