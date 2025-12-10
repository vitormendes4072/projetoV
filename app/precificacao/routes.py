# app/precificacao/routes.py
from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from app import db
from app.models.pricing import PricingHistory # Importe o modelo novo
from .forms import CalculatorForm

pricing = Blueprint('pricing', __name__)

@pricing.route('/calculator', methods=['GET', 'POST'])
@login_required
def calculator():
    form = CalculatorForm()
    results = None
    
    # Preenchimento via URL (Mantido)
    if request.method == 'GET':
        price_arg = request.args.get('price')
        cost_arg = request.args.get('cost')
        if price_arg: form.price.data = float(price_arg)
        if cost_arg: form.cost.data = float(cost_arg)
    
    if form.validate_on_submit():
        # Cálculos (Mantidos)
        price = form.price.data
        cost = form.cost.data
        fba_fee = form.fba_fee.data
        referral_pct = form.referral_fee.data
        tax_pct = form.tax_rate.data
        marketing = form.marketing.data or 0
        
        referral_cost = price * (referral_pct / 100)
        tax_cost = price * (tax_pct / 100)
        total_fees = referral_cost + fba_fee + tax_cost + marketing
        total_cost = cost + total_fees
        net_profit = price - total_cost
        
        margin = (net_profit / price) * 100 if price > 0 else 0
        roi = (net_profit / cost) * 100 if cost > 0 else 0
        
        results = {
            'revenue': price,
            'total_cost': total_cost,
            'net_profit': net_profit,
            'margin': margin,
            'roi': roi,
            'breakdown': {
                'referral': referral_cost,
                'fba': fba_fee,
                'tax': tax_cost,
                'marketing': marketing,
                'product_cost': cost
            }
        }

        # --- LÓGICA DE SALVAR ---
        # Verifica se o botão clicado foi o de salvar
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
                net_profit=net_profit,
                margin=margin,
                roi=roi
            )
            db.session.add(historico)
            db.session.commit()
            flash('Simulação salva no histórico!', 'success')
            # Redireciona para limpar o POST (PRG Pattern)
            return redirect(url_for('pricing.calculator'))

    # Carrega o histórico para mostrar na tela (Últimos 10)
    history_items = PricingHistory.query.filter_by(user_id=current_user.id).order_by(PricingHistory.created_at.desc()).limit(10).all()

    return render_template('calculator.html', form=form, results=results, history=history_items)