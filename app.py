"""Optional local frontend preview; no database, API, login or authentication."""
from flask import Flask, render_template, request
from calculations import (total_demand, compare_suppliers, procurement_cost,
                          landed_cost_per_kg, savings_percentage)
from sample_data import ORDERS, SUPPLIERS

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
    if request.method == 'GET' and recommended:
        savings = savings_percentage(baseline, recommended['total_cost'])
    return render_template('index.html', orders=example_orders,
                           suppliers=result['results'], quantity=quantity,
                           recommended=recommended, baseline=baseline,
                           savings=savings, error=error, custom=custom)

@app.route('/method')
def method():
    return render_template('method.html')

if __name__ == '__main__':
    app.run(debug=True)
