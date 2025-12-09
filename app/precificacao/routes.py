# app/precificacao/routes.py
from flask import Blueprint, render_template
from flask_login import login_required
from .forms import CalculatorForm

# Define o Blueprint 'pricing' (ou precificacao)
pricing = Blueprint('pricing', __name__)

@pricing.route('/calculator', methods=['GET', 'POST'])
@login_required
def calculator():
    form = CalculatorForm()
    results = None
    
    if form.validate_on_submit():
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
    return render_template('calculator.html', form=form, results=results)