"""BUTCHERBRIDGE - SUPPLY CHAIN CALCULATIONS

This file is the independent supply-chain model for the semester project.
It deliberately does NOT import Flask, HTML, or database libraries.

Business idea: Several butcheries can combine orders for the SAME product.
A larger combined order may qualify for a lower supplier price per kilogram.
We compare the full delivered cost, not only the advertised meat price.

Monetary amounts are South African rand (R); quantities are kilograms (kg).
Sample numbers are for classroom demonstration, not real supplier quotes.
"""

def check_positive(value, name):
    """Convert a number to float and reject zero or negative amounts."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(name + " must be a number")
    if number <= 0:
        raise ValueError(name + " must be greater than zero")
    return number


def check_non_negative(value, name):
    """Costs can equal zero, but cannot be negative."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(name + " must be a number")
    if number < 0:
        raise ValueError(name + " cannot be negative")
    return number


def total_demand(quantities):
    """FORMULA 1 - Demand aggregation: Q_group = q1 + q2 + ... + qn.

    Input: a list of confirmed orders, in kg, for the SAME product.
    Assumption: quantities refer to compatible product specifications.
    Example: [100, 150, 250] gives 500 kg.
    """
    if not quantities:
        raise ValueError("Please supply at least one retailer order")
    return round(sum(check_positive(q, "order quantity") for q in quantities), 2)


def unit_price_for_quantity(quantity_kg, price_tiers):
    """FORMULA 2 - Volume-based supplier pricing.

    Choose price for the highest minimum-kg threshold that is met.
    Example tiers: [(1, 95), (300, 88), (500, 82)].
    An order of 500 kg qualifies for R82/kg; a 200 kg order for R95/kg.
    If the supplier has no eligible tier, report an error.
    """
    quantity = check_positive(quantity_kg, "quantity")
    if not price_tiers:
        raise ValueError("A supplier needs at least one price tier")
    eligible = []
    for minimum, price in price_tiers:
        minimum = check_positive(minimum, "minimum tier quantity")
        price = check_non_negative(price, "price per kg")
        if quantity >= minimum:
            eligible.append((minimum, price))
    if not eligible:
        raise ValueError("Order quantity does not qualify for a price tier")
    return max(eligible, key=lambda tier: tier[0])[1]


def procurement_cost(quantity_kg, price_per_kg, fixed_delivery, variable_delivery_per_kg=0, handling=0):
    """FORMULA 3 - Total landed procurement cost (rand).

    TC = (Q x P) + F + (Q x V) + H
    Q = quantity ordered (kg)
    P = supplier meat price (R/kg)
    F = fixed delivery charge (R)
    V = additional delivery charge per kg (R/kg)
    H = handling cost (R)

    Assumption: there are no taxes or extra costs unless added to inputs.
    """
    q = check_positive(quantity_kg, "quantity")
    p = check_non_negative(price_per_kg, "price per kg")
    f = check_non_negative(fixed_delivery, "fixed delivery")
    v = check_non_negative(variable_delivery_per_kg, "variable delivery")
    h = check_non_negative(handling, "handling")
    return round(q * p + f + q * v + h, 2)


def landed_cost_per_kg(total_cost, quantity_kg):
    """FORMULA 4 - Delivered cost per kg: LC = TC / Q.

    This is a fairer supplier comparison than price per kg alone,
    because delivery and handling fees are included.
    """
    total = check_non_negative(total_cost, "total cost")
    q = check_positive(quantity_kg, "quantity")
    return round(total / q, 2)


def savings_percentage(baseline_cost, proposed_cost):
    """FORMULA 5 - Percentage saving: S = (Old - New) / Old x 100.

    A negative result indicates the new option costs MORE.
    The old (baseline) cost must be greater than zero.
    """
    old = check_positive(baseline_cost, "baseline cost")
    new = check_non_negative(proposed_cost, "proposed cost")
    return round((old - new) / old * 100, 2)


def supplier_is_feasible(quantity_kg, capacity_kg, lead_days, days_available,
                         expected_fill_rate, minimum_fill_rate=0.95):
    """FORMULA 6 - Supplier feasibility check.

    A supplier qualifies only if ALL checks are true:
    Q <= supplier capacity; lead days <= days until needed;
    expected fill rate >= the minimum required fill rate.
    Rates are decimals, e.g. 0.97 represents 97%.
    """
    q = check_positive(quantity_kg, "quantity")
    capacity = check_non_negative(capacity_kg, "capacity")
    lead = check_non_negative(lead_days, "lead time")
    available = check_non_negative(days_available, "days available")
    rate = check_non_negative(expected_fill_rate, "fill rate")
    minimum = check_non_negative(minimum_fill_rate, "minimum fill rate")
    if rate > 1 or minimum > 1:
        raise ValueError("Fill rates must be between 0 and 1")
    return q <= capacity and lead <= available and rate >= minimum


def compare_suppliers(quantity_kg, suppliers, days_available=7, minimum_fill_rate=0.95):
    """Compare eligible suppliers by TOTAL LANDED COST per kg.

    Each supplier needs: name, capacity_kg, lead_days, fill_rate,
    price_tiers, delivery, variable_delivery, handling.
    The cheapest FEASIBLE supplier is recommended.
    Invalid suppliers are shown with a reason rather than disappearing.
    """
    q = check_positive(quantity_kg, "quantity")
    if not suppliers:
        raise ValueError("At least one supplier must be entered")
    results = []
    for supplier in suppliers:
        name = supplier["name"]
        reasons = []
        if q > check_non_negative(supplier["capacity_kg"], "capacity"):
            reasons.append("Not enough capacity")
        if check_non_negative(supplier["lead_days"], "lead time") > days_available:
            reasons.append("Delivery would be late")
        fill = check_non_negative(supplier["fill_rate"], "fill rate")
        if fill > 1:
            raise ValueError("Fill rates must be between 0 and 1")
        if fill < minimum_fill_rate:
            reasons.append("Fill rate too low")
        try:
            price = unit_price_for_quantity(q, supplier["price_tiers"])
        except ValueError:
            price = None
            reasons.append("No qualifying price tier")
        cost = None
        landed = None
        if price is not None:
            cost = procurement_cost(q, price, supplier.get("delivery", 0),
                                    supplier.get("variable_delivery", 0),
                                    supplier.get("handling", 0))
            landed = landed_cost_per_kg(cost, q)
        results.append({"name": name, "price": price, "total_cost": cost,
                        "landed_per_kg": landed, "eligible": not reasons,
                        "reason": ", ".join(reasons) if reasons else "Meets requirements"})
    eligible = [r for r in results if r["eligible"]]
    recommended = min(eligible, key=lambda r: r["total_cost"]) if eligible else None
    return {"results": results, "recommended": recommended}


def share_fixed_cost(fixed_cost, retailer_kg, group_kg):
    """FORMULA 7 - Proportional shared delivery cost: Share_i = F x (q_i / Q).

    Allocates group fixed costs in proportion to each retailer's kg.
    Small rounding differences may occur when individual shares are added.
    """
    f = check_non_negative(fixed_cost, "fixed cost")
    q = check_positive(retailer_kg, "retailer quantity")
    group = check_positive(group_kg, "group quantity")
    if q > group:
        raise ValueError("Retailer quantity cannot exceed group demand")
    return round(f * q / group, 2)
