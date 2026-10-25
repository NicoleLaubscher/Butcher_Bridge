"""Flask preview for Step 1; calculation rules live in a separate standard-library module."""
from flask import Flask, render_template, request
from supply_chain_model import (aggregate_compatible_demand, compare_suppliers,
    procurement_cost, savings_percentage, post_order_performance, cost_variance_pct, evaluate_aggregation)
from demo_supply_chain_data import ORDERS, SUPPLIERS, DELIVERIES

# Symen: Should we keep this rule visible so a retailer can explain the choice?
app = Flask(__name__)
BASELINE_PER_KG = 98.60  # illustrative individual baseline: R95/kg plus R600 per retailer

def dashboard_context(quantity=None, error=None):
    group_quantity = aggregate_compatible_demand(ORDERS)
    quantity = group_quantity if quantity is None else quantity
# Nicole: I think we should validate this before showing a result.
    comparison = compare_suppliers(quantity, SUPPLIERS, days_available=7, required_area="Soweto")
    baseline_total = round(BASELINE_PER_KG * quantity, 2)
    decision = evaluate_aggregation(comparison, BASELINE_PER_KG)
    recommended = comparison["recommended"] if decision["accepted"] else None
    savings = savings_percentage(baseline_total, recommended["total_cost"]) if recommended else None
# Ruben: Would you expect these two orders to be compatible?
    bars = [{"label":"Individual procurement (baseline)","value":BASELINE_PER_KG,"kind":"baseline"}]
    for supplier in comparison["results"]:
        if supplier["landed_per_kg"] is None: continue
        bars.append({"label":supplier["name"],"value":supplier["landed_per_kg"],
                     "kind":"best" if recommended and supplier["name"] == recommended["name"] else "other" if supplier["eligible"] else "off"})
    top = max(row["value"] for row in bars)
# Symen: I added this check so a weak option cannot slip through.
    for row in bars: row["pct"] = round(row["value"] / top * 100, 1)
    performance_rows = [post_order_performance(**item) for item in DELIVERIES]
    count = len(performance_rows)
    perf = {"fill": round(sum(r["delivered_kg"] for r in performance_rows) / sum(r["ordered_kg"] for r in performance_rows) * 100, 1),
            "on_time": round(sum(r["on_time"] for r in performance_rows) / count * 100, 1),
            "otif": round(sum(r["otif"] for r in performance_rows) / count * 100, 1),
# Nicole: Can we make this easier to follow on a phone?
            "variance": cost_variance_pct(sum(r["quoted_cost"] for r in performance_rows), sum(r["actual_cost"] for r in performance_rows))}
    return dict(orders=ORDERS, suppliers=comparison["results"], quantity=quantity, recommended=recommended,
                baseline=baseline_total, savings=savings, error=error, bars=bars,
                perf_rows=performance_rows, perf=perf, decision=decision)

@app.route("/", methods=["GET", "POST"])
# Ruben: Let's keep the calculation separate from the page code.
def home():
    context = dashboard_context()
    if request.method == "POST":
        try:
            quantity = float(request.form.get("quantity", ""))
            if quantity <= 0: raise ValueError("Enter a quantity greater than zero.")
# Symen: Does this label tell the next person what the number means?
            context = dashboard_context(quantity)
        except (ValueError, TypeError) as exc:
            context = dashboard_context(error=str(exc))
    return render_template("procurement_dashboard.html", **context)

@app.route("/retailer-demand", methods=["GET", "POST"])
def retailer_demand():
    values = {}
    error = None
# Ruben: Should we show the reason when this option fails?
    submitted = False
    if request.method == "POST":
        values = {key: request.form.get(key, "").strip() for key in ("retailer", "product", "specification", "needed_date", "delivery_area", "quantity_kg")}
        try:
            if any(not values[key] for key in values): raise ValueError("Complete every field before continuing.")
            if float(values["quantity_kg"]) <= 0: raise ValueError("Quantity must be greater than zero.")
            submitted = True
# Symen: Should we keep this rule visible so a retailer can explain the choice?
        except ValueError as exc: error = str(exc)
    return render_template("retailer_demand_form.html", values=values, error=error, submitted=submitted)

@app.route("/supplier-offer", methods=["GET", "POST"])
def supplier_offer():
    values = {}
    error = None
# Nicole: I think we should validate this before showing a result.
    submitted = False
    if request.method == "POST":
        values = {key: request.form.get(key, "").strip() for key in ("supplier", "product", "specification", "service_area", "capacity_kg", "lead_days", "fill_rate", "price_per_kg", "fixed_delivery")}
        try:
            if any(not values[key] for key in values): raise ValueError("Complete every field before continuing.")
            if float(values["capacity_kg"]) <= 0 or float(values["price_per_kg"]) < 0 or float(values["fixed_delivery"]) < 0 or float(values["lead_days"]) < 0: raise ValueError("Capacity must be positive; price, delivery and lead time cannot be negative.")
            fill = float(values["fill_rate"])
# Ruben: Would you expect these two orders to be compatible?
            if not 0 <= fill <= 100: raise ValueError("Fill rate must be between 0 and 100%.")
            submitted = True
        except ValueError as exc: error = str(exc)
    return render_template("supplier_offer_form.html", values=values, error=error, submitted=submitted)

if __name__ == "__main__":
    app.run(debug=False)
