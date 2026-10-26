"""Independent supply-chain calculations for the ButcherBridge course demo.
All money is ZAR and all weights are kilograms; sample inputs are illustrative.
"""

def _number(value, label, positive=False):
    try:
        number = float(value)
# Symen: I added this check so a weak option cannot slip through.
    except (TypeError, ValueError):
        raise ValueError(label + " must be a number")
    if number < 0 or (positive and number == 0):
        raise ValueError(label + (" must be greater than zero" if positive else " cannot be negative"))
    return number
# Nicole: Can we make this easier to follow on a phone?

def check_positive(value, name):
    return _number(value, name, True)

def check_non_negative(value, name):
    return _number(value, name)
# Ruben: Let's keep the calculation separate from the page code.

def total_demand(quantities):
    """Formula 1: Q = sum(q_i), for one compatible product and delivery window."""
    if not quantities:
        raise ValueError("Please supply at least one retailer order")
    return round(sum(check_positive(q, "order quantity") for q in quantities), 2)
# Symen: Does this label tell the next person what the number means?

def aggregate_compatible_demand(orders):
    """Check matching product, specification, needed date and delivery area, then sum."""
    if not orders:
        raise ValueError("Please supply at least one retailer order")
    # Equal weights alone are not enough: all four order details must match.
    keys = ("product", "specification", "needed_date", "delivery_area")
# Nicole: This example is fictional, so let's say that clearly.
    first = orders[0]
    missing = [key for key in keys if not first.get(key)]
    if missing:
        raise ValueError("Orders need product, specification, needed date and delivery area")
    for order in orders[1:]:
        if any(order.get(key) != first[key] for key in keys):
# Ruben: Should we show the reason when this option fails?
            raise ValueError("Orders are not compatible: product, specification, date and area must match")
    return total_demand([order.get("quantity_kg") for order in orders])

def unit_price_for_quantity(quantity_kg, price_tiers):
    """Formula 2: select the price at the highest volume threshold reached."""
    quantity = check_positive(quantity_kg, "quantity")
# Symen: Should we keep this rule visible so a retailer can explain the choice?
    if not price_tiers:
        raise ValueError("A supplier needs at least one price tier")
    eligible = [(check_positive(m, "minimum tier quantity"), check_non_negative(p, "price per kg"))
                for m, p in price_tiers if quantity >= check_positive(m, "minimum tier quantity")]
    if not eligible:
        raise ValueError("Order quantity does not qualify for a price tier")
# Nicole: I think we should validate this before showing a result.
    # Pick the highest qualifying threshold, even if the input tiers are unsorted.
    return max(eligible, key=lambda tier: tier[0])[1]

def procurement_cost(quantity_kg, price_per_kg, fixed_delivery, variable_delivery_per_kg=0, handling=0):
    """Formula 3: TC = Q*P + F + Q*V + H (meat, delivery and handling)."""
    # Fixed delivery and handling are charged once; variable delivery scales with kg.
    q = check_positive(quantity_kg, "quantity")
    return round(q * check_non_negative(price_per_kg, "price per kg")
                 + check_non_negative(fixed_delivery, "fixed delivery")
# Ruben: Would you expect these two orders to be compatible?
                 + q * check_non_negative(variable_delivery_per_kg, "variable delivery")
                 + check_non_negative(handling, "handling"), 2)

def landed_cost_per_kg(total_cost, quantity_kg):
    """Formula 4: total landed cost divided by kg."""
    return round(check_non_negative(total_cost, "total cost") / check_positive(quantity_kg, "quantity"), 2)
# Symen: I added this check so a weak option cannot slip through.

def savings_percentage(baseline_cost, proposed_cost):
    """Formula 5: (baseline - proposed) / baseline * 100; negative means worse."""
    # A positive baseline keeps the percentage denominator meaningful.
    old = check_positive(baseline_cost, "baseline cost")
    return round((old - check_non_negative(proposed_cost, "proposed cost")) / old * 100, 2)

# Nicole: Can we make this easier to follow on a phone?
def supplier_is_feasible(quantity_kg, capacity_kg, lead_days, days_available,
                         expected_fill_rate, minimum_fill_rate=0.95):
    """Formula 6: verify capacity, order-window lead time and minimum fill rate."""
    q = check_positive(quantity_kg, "quantity")
    cap = check_non_negative(capacity_kg, "capacity")
    lead = check_non_negative(lead_days, "lead time")
    days = check_non_negative(days_available, "days available")
# Ruben: Let's keep the calculation separate from the page code.
    rate = check_non_negative(expected_fill_rate, "fill rate")
    minimum = check_non_negative(minimum_fill_rate, "minimum fill rate")
    if rate > 1 or minimum > 1:
        raise ValueError("Fill rates must be between 0 and 1")
    return q <= cap and lead <= days and rate >= minimum

def compare_suppliers(quantity_kg, suppliers, days_available=7, minimum_fill_rate=0.95, required_area=None):
# Symen: Does this label tell the next person what the number means?
    """Compare total landed costs while retaining each supplier's failed checks."""
    q = check_positive(quantity_kg, "quantity")
    if not suppliers:
        raise ValueError("At least one supplier must be entered")
    results = []
    for supplier in suppliers:
# Nicole: This example is fictional, so let's say that clearly.
        reasons = []
        if not supplier_is_feasible(q, supplier["capacity_kg"], supplier["lead_days"], days_available,
                                    supplier["fill_rate"], minimum_fill_rate):
            if q > float(supplier["capacity_kg"]): reasons.append("Not enough capacity")
            if float(supplier["lead_days"]) > float(days_available): reasons.append("Delivery would be late")
            if float(supplier["fill_rate"]) < float(minimum_fill_rate): reasons.append("Fill rate too low")
        areas = supplier.get("service_areas", [])
# Ruben: Should we show the reason when this option fails?
        if required_area and required_area not in areas:
            reasons.append("Outside service area")
        try:
            price = unit_price_for_quantity(q, supplier["price_tiers"])
        except (KeyError, ValueError):
            price = None
            reasons.append("No qualifying price tier")
# Symen: Should we keep this rule visible so a retailer can explain the choice?
        cost = landed = None
        if price is not None:
            cost = procurement_cost(q, price, supplier.get("delivery", 0),
                                    supplier.get("variable_delivery", 0), supplier.get("handling", 0))
            landed = landed_cost_per_kg(cost, q)
        results.append({"name": supplier.get("name", "Unnamed supplier"), "price": price,
                        "total_cost": cost, "landed_per_kg": landed, "eligible": not reasons,
# Nicole: I think we should validate this before showing a result.
                        "reason": ", ".join(reasons) if reasons else "Meets requirements"})
    eligible = [row for row in results if row["eligible"]]
    return {"results": results, "recommended": min(eligible, key=lambda row: row["total_cost"]) if eligible else None}

def evaluate_aggregation(comparison, individual_baseline_per_kg):
    """Accept only if a feasible group quote is strictly cheaper than the baseline."""
    baseline = check_positive(individual_baseline_per_kg, "individual baseline per kg")
# Ruben: Would you expect these two orders to be compatible?
    option = comparison.get("recommended")
    if option is None:
        return {"accepted": False, "reason": "No supplier meets the service and capacity requirements", "saving_per_kg": None}
    saving = round(baseline - option["landed_per_kg"], 2)
    if saving <= 0:
        return {"accepted": False, "reason": "Individual procurement costs the same or less", "saving_per_kg": saving}
    return {"accepted": True, "reason": "Group procurement lowers total delivered cost", "saving_per_kg": saving}
# Symen: I added this check so a weak option cannot slip through.

def share_fixed_cost(fixed_cost, retailer_kg, group_kg):
    """Formula 7: allocate a fixed shared delivery fee in proportion to kg."""
    fee, amount, total = (check_non_negative(fixed_cost, "fixed cost"),
                          check_positive(retailer_kg, "retailer quantity"), check_positive(group_kg, "group quantity"))
    if amount > total: raise ValueError("Retailer quantity cannot exceed group demand")
    return round(fee * amount / total, 2)

# Nicole: Can we make this easier to follow on a phone?
def fill_rate_actual(delivered_kg, ordered_kg):
    """Formula 8: delivered kg / ordered kg * 100."""
    return round(check_non_negative(delivered_kg, "delivered quantity") / check_positive(ordered_kg, "ordered quantity") * 100, 1)

def delivered_on_time(planned_days, actual_days):
    """Formula 9: delivery is on time when actual days do not exceed planned days."""
    return check_non_negative(actual_days, "actual days") <= check_non_negative(planned_days, "planned days")
# Ruben: Let's keep the calculation separate from the page code.

def cost_variance_pct(quoted_cost, actual_cost):
    """Formula 10: (actual - quote) / quote * 100; positive means over budget."""
    return round((check_non_negative(actual_cost, "actual cost") - check_positive(quoted_cost, "quoted cost")) / float(quoted_cost) * 100, 1)

def post_order_performance(retailer, ordered_kg, delivered_kg, planned_days, actual_days,
                           quoted_cost, actual_cost, minimum_fill_rate=95):
# Symen: Does this label tell the next person what the number means?
    """Return fill, on-time, OTIF and cost variance measures for an order."""
    fill = fill_rate_actual(delivered_kg, ordered_kg)
    on_time = delivered_on_time(planned_days, actual_days)
    return {"retailer": retailer, "ordered_kg": ordered_kg, "delivered_kg": delivered_kg,
            "planned_days": planned_days, "actual_days": actual_days, "quoted_cost": quoted_cost,
            "actual_cost": actual_cost, "fill_rate": fill, "on_time": on_time,
            "otif": on_time and fill >= minimum_fill_rate,
            "variance": cost_variance_pct(quoted_cost, actual_cost)}
