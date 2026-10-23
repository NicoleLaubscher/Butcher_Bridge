"""Optional local frontend preview; no database, API, login or authentication."""
from flask import Flask, render_template, request
from calculations import (total_demand, compare_suppliers, procurement_cost,
                          landed_cost_per_kg, savings_percentage)
from sample_data import ORDERS, SUPPLIERS

from calculations import (total_demand, compare_suppliers, procurement_cost,
                          landed_cost_per_kg, savings_percentage,
                          post_order_performance, cost_variance_pct)
from sample_data import ORDERS, SUPPLIERS, DELIVERIES

app = Flask(__name__)

@app.route('/', methods=['GET', 'POST'])
def home():
    example_orders = ORDERS
    quantity = total_demand([order['quantity_kg'] for order in example_orders])
    result = compare_suppliers(quantity, SUPPLIERS)
    # Classroom baseline: each retailer purchases individually at R95/kg,
    # plus one R600 delivery charge per retailer.
    baseline = sum(procurement_cost(o['quantity_kg'], 95, 600)
                   for o in example_orders)
    baseline_per_kg = round(baseline / quantity, 2)
    error = None
    custom = None
    if request.method == 'POST':
        try:
            quantity = float(request.form.get('quantity', '0'))
            result = compare_suppliers(quantity, SUPPLIERS)
            if result['recommended']:
                custom = result['recommended']
            else:
                error = 'None of the sample suppliers can meet that order.'
        except (ValueError, TypeError) as exc:
            error = str(exc)
    recommended = result['recommended']
    savings = None
    if recommended:
        savings = savings_percentage(baseline_per_kg * quantity,
                                     recommended['total_cost'])
    bars = [{"label": "Individual procurement (baseline)",
             "value": baseline_per_kg, "kind": "baseline"}]
    for s in result['results']:
        if s['landed_per_kg'] is None:
            continue
        is_best = bool(recommended) and s['name'] == recommended['name']
        label = s['name'] + (" (recommended)" if is_best else
                             "" if s['eligible'] else " (not eligible)")
        kind = "best" if is_best else ("other" if s['eligible'] else "off")
        bars.append({"label": label, "value": s['landed_per_kg'], "kind": kind})
    top = max(b['value'] for b in bars)
    for b in bars:
        b['pct'] = round(b['value'] / top * 100, 1)
        perf_rows = [post_order_performance(**d) for d in DELIVERIES]
    n = len(perf_rows)
    perf = {
        "fill": round(sum(r['delivered_kg'] for r in perf_rows) /
                      sum(r['ordered_kg'] for r in perf_rows) * 100, 1),
        "on_time": round(sum(r['on_time'] for r in perf_rows) / n * 100, 1),
        "otif": round(sum(r['otif'] for r in perf_rows) / n * 100, 1),
        "variance": cost_variance_pct(sum(r['quoted_cost'] for r in perf_rows),
                                      sum(r['actual_cost'] for r in perf_rows)),
    }
    return render_template('index.html', orders=example_orders,
                           suppliers=result['results'], quantity=quantity,
                           recommended=recommended, baseline=baseline,
                           savings=savings, error=error, custom=custom, bars=bars, perf_rows=perf_rows, perf=perf)

@app.route('/method')
def method():
    from flask import abort
    abort(404)

if __name__ == '__main__':
    app.run(debug=True)
