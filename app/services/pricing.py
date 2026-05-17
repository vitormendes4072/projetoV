def calcular_fba(price, cost, fba_fee, referral_pct, tax_pct, marketing=0) -> dict:
    referral_cost = price * (referral_pct / 100)
    tax_cost      = price * (tax_pct / 100)
    total_fees    = referral_cost + fba_fee + tax_cost + marketing
    total_cost    = cost + total_fees
    net_profit    = price - total_cost
    margin = (net_profit / price) * 100 if price > 0 else 0
    roi    = (net_profit / cost)  * 100 if cost  > 0 else 0
    return {
        "revenue":    price,
        "total_cost": total_cost,
        "net_profit": net_profit,
        "margin":     margin,
        "roi":        roi,
        "breakdown": {
            "referral":     referral_cost,
            "fba":          fba_fee,
            "tax":          tax_cost,
            "marketing":    marketing,
            "product_cost": cost,
        },
    }
