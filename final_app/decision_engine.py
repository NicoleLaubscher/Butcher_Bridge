
"""Deterministic procurement evaluator; no database or network dependencies."""

from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

if __package__:
    from .joint_capacity_planner import plan_offers
else:
    from joint_capacity_planner import plan_offers


def D(value):
    return Decimal(str(value))


def _round_money(value):
    return D(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def money(value):
    return float(_round_money(value))


def validate_order(order):
    """Reject invalid committed demand before procurement evaluation."""
    order_id = order.get("id", "unknown")
    if order.get("retailer_id") in (None, ""):
        raise ValueError(f"Order {order_id}: retailer_id is required")

    numeric_fields = (
        "quantity_kg", "baseline_price_per_kg", "baseline_logistics_cost",
        "baseline_trips", "baseline_distance_km",
    )
    for field in numeric_fields:
        try:
            value = D(order[field])
        except (KeyError, TypeError, ValueError, ArithmeticError):
            raise ValueError(f"Order {order_id}: invalid {field}") from None
        if not value.is_finite():
            raise ValueError(f"Order {order_id}: {field} must be finite")
        if field == "quantity_kg":
            if value <= 0:
                raise ValueError(f"Order {order_id}: quantity_kg must be positive")
        elif value < 0:
            raise ValueError(f"Order {order_id}: {field} cannot be negative")

    trips = D(order["baseline_trips"])
    if trips != trips.to_integral_value():
        raise ValueError(f"Order {order_id}: baseline_trips must be a whole number")


def validate_supplier_number(value, field, *, positive=False,
                             whole_number=False, maximum=None):
    """Require a finite numeric supplier value within its permitted bounds."""
    try:
        number = D(value)
    except (TypeError, ValueError, ArithmeticError):
        raise ValueError(f"{field} must be a valid number") from None

    if not number.is_finite():
        raise ValueError(f"{field} must be finite")
    if positive and number <= 0:
        raise ValueError(f"{field} must be positive")
    if not positive and number < 0:
        raise ValueError(f"{field} cannot be negative")
    if whole_number and number != number.to_integral_value():
        raise ValueError(f"{field} must be a whole number")
    if maximum is not None and number > D(maximum):
        raise ValueError(f"{field} cannot exceed {maximum}")

    return number


def validate_supplier_inputs(offers, tiers, reserved, min_fill):
    """Validate supplier offers, price tiers, and reserved quantities."""
    validate_supplier_number(min_fill, "min_fill", maximum=1)

    for offer in offers:
        prefix = f"Offer {offer.get('id', 'unknown')}"

        validate_supplier_number(
            offer["capacity_kg"], f"{prefix} capacity_kg", positive=True
        )
        validate_supplier_number(
            offer["lead_days"], f"{prefix} lead_days", whole_number=True
        )
        validate_supplier_number(
            offer["fill_rate"], f"{prefix} fill_rate", maximum=1
        )

        for field in (
            "fixed_delivery",
            "variable_delivery_per_kg",
            "handling_cost",
            "coordinated_distance_km",
        ):
            validate_supplier_number(offer[field], f"{prefix} {field}")

        validate_supplier_number(
            offer["coordinated_trips"],
            f"{prefix} coordinated_trips",
            whole_number=True,
        )

    seen_tiers = set()

    for tier in tiers:
        offer_id = tier["offer_id"]

        threshold = validate_supplier_number(
            tier["min_quantity_kg"],
            f"Offer {offer_id} min_quantity_kg",
            positive=True,
        )

        validate_supplier_number(
            tier["price_per_kg"],
            f"Offer {offer_id} price_per_kg",
        )

        tier_key = (offer_id, threshold)

        if tier_key in seen_tiers:
            raise ValueError(
                f"Offer {offer_id}: duplicate price tier threshold"
            )

        seen_tiers.add(tier_key)

    for reservation_key, quantity in reserved.items():
        if (
            not isinstance(reservation_key, tuple)
            or len(reservation_key) != 2
        ):
            raise ValueError(
                "Reservation key must contain offer_id and window_id"
            )

        validate_supplier_number(
            quantity,
            f"Reservation {reservation_key} quantity_kg",
        )


def evaluate(orders, offers, tiers, reserved=None, min_fill=0.95, as_of=None):
    """Propose capacity-feasible procurement for pre-formed compatible batches."""
    as_of = as_of or date.today()
    reserved = reserved or {}

    validate_supplier_inputs(offers, tiers, reserved, min_fill)

    reserved_by_offer = defaultdict(Decimal)
    for (offer_id, _window_id), quantity in reserved.items():
        reserved_by_offer[offer_id] += D(quantity)

    offers = sorted(offers, key=lambda offer: offer["id"])
    available_by_offer = {
        offer["id"]: D(offer["capacity_kg"]) - reserved_by_offer[offer["id"]]
        for offer in offers
    }

    groups = defaultdict(list)

    for o in orders:
        if o["status"] != "committed":
            continue

        validate_order(o)

        key = (
            o["window_id"],
            o["product_id"],
            str(o["needed_date"]),
            o["delivery_area"],
        )

        groups[key].append(o)

    batches = []
    planner_inputs = []

    for key, batch in sorted(groups.items()):
        _, product, need, area = key
        batch = sorted(batch, key=lambda order: order["id"], reverse=True)
        q = sum(D(o["quantity_kg"]) for o in batch)

        baseline = sum(
            D(o["quantity_kg"]) * D(o["baseline_price_per_kg"])
            + D(o["baseline_logistics_cost"])
            for o in batch
        )

        quotes = {}

        for offer in offers:
            if offer["product_id"] != product or not offer["active"]:
                continue

            reasons = []

            available = available_by_offer[offer["id"]]

            if available < q:
                reasons.append("Insufficient unreserved capacity")

            if offer["service_area"].casefold() != area.casefold():
                reasons.append("Outside service area")

            days_available = (date.fromisoformat(need) - as_of).days

            if (
                days_available < 0
                or int(offer["lead_days"]) > days_available
            ):
                reasons.append("Lead time exceeds required date")

            if D(offer["fill_rate"]) < D(min_fill):
                reasons.append("Below minimum expected fill rate")

            eligible_tiers = [
                t for t in tiers
                if (
                    t["offer_id"] == offer["id"]
                    and D(t["min_quantity_kg"]) <= q
                )
            ]

            best_tier = (
                max(
                    eligible_tiers,
                    key=lambda t: D(t["min_quantity_kg"]),
                )
                if eligible_tiers
                else None
            )

            if best_tier is None:
                reasons.append("No qualifying price tier")

            total = None

            if best_tier:
                total = (
                    q * D(best_tier["price_per_kg"])
                    + D(offer["fixed_delivery"])
                    + q * D(offer["variable_delivery_per_kg"])
                    + D(offer["handling_cost"])
                )

            quotes[offer["id"]] = {
                "offer_id": offer["id"],
                "supplier": offer["supplier_name"],
                "eligible": not reasons,
                "reasons": reasons,
                "total_cost": (
                    _round_money(total) if total is not None else None
                ),
                "cost_per_kg": (
                    money(total / q) if total is not None else None
                ),
                "tier_min_kg": (
                    float(best_tier["min_quantity_kg"])
                    if best_tier else None
                ),
                "available_kg": float(available),
                "delivery_trips": int(offer["coordinated_trips"]),
                "distance_km": float(offer["coordinated_distance_km"]),
            }

        savings = {
            offer_id: baseline - quote["total_cost"]
            for offer_id, quote in quotes.items()
            if quote["eligible"] and quote["total_cost"] < baseline
        }
        batches.append((key, batch, baseline, quotes))
        planner_inputs.append((q, savings))

    plan = plan_offers(planner_inputs, available_by_offer)
    outputs = []

    for index, (key, batch, baseline, quotes) in enumerate(batches):
        window, product, need, area = key
        q, savings = planner_inputs[index]
        proposed_offer_id = plan.get(index) if plan is not None else None
        base_trips = sum(int(o["baseline_trips"]) for o in batch)
        base_distance = sum(D(o["baseline_distance_km"]) for o in batch)

        retailer_count = len({
            o["retailer_id"] for o in batch
        })

        if proposed_offer_id is not None:
            best = quotes[proposed_offer_id]
            if retailer_count == 1:
                decision = "INDIVIDUAL_BETTER_QUOTE"
                reason = (
                    "The lowest-cost joint plan proposes this supplier quote "
                    "for the retailer's individual procurement."
                )
            else:
                decision = "ACCEPT"
                reason = (
                    "The lowest-cost joint plan proposes this supplier quote "
                    "for multi-retailer aggregation."
                )

        elif savings:
            best = None
            if plan is None:
                decision = "REJECT_PLANNING_LIMIT"
                reason = (
                    "This scenario exceeds the joint planning limit. Keep the "
                    "individual procurement baseline."
                )
            else:
                decision = "REJECT_NO_FEASIBLE_SUPPLIER"
                reason = (
                    "The lowest-cost joint plan uses shared capacity for "
                    "other batches. Keep the individual procurement baseline."
                )

        else:
            best = min(
                (quote for quote in quotes.values() if quote["eligible"]),
                key=lambda quote: quote["total_cost"],
                default=None,
            )
            if best is None:
                decision = "REJECT_NO_FEASIBLE_SUPPLIER"
                reason = (
                    "No eligible supplier satisfies the procurement "
                    "requirements. Retailers should retain their "
                    "existing procurement arrangements."
                )
            elif retailer_count == 1:
                decision = "INDIVIDUAL_KEEP_BASELINE"
                reason = (
                    "Only one retailer is participating. The retailer should "
                    "retain its existing procurement arrangement because it "
                    "is cheaper than or equal in cost to the alternative "
                    "supplier quotation."
                )
            else:
                decision = "REJECT_NOT_CHEAPER"
                reason = (
                    "Multi-retailer aggregation does not reduce total delivered "
                    "procurement cost. Retailers should retain their existing "
                    "procurement arrangements."
                )

        group_cost = best["total_cost"] if best is not None else None

        allocated = []

        if best is not None:
            shares = [
                _round_money(group_cost * D(o["quantity_kg"]) / q)
                for o in batch[:-1]
            ]

            shares.append(group_cost - sum(shares))

            allocated = [
                {
                    "order_id": o["id"],
                    "retailer": o["retailer_name"],
                    "allocated_cost": money(c),
                }
                for o, c in zip(batch, shares)
            ]

        savings_pct = (
            money((baseline - group_cost) / baseline * 100)
            if group_cost is not None and baseline > 0
            else None
        )

        recommended_savings_pct = savings_pct if proposed_offer_id is not None else 0.0

        # Keep public quote costs numeric while using Decimal for plan comparisons.
        for quote in quotes.values():
            if quote["total_cost"] is not None:
                quote["total_cost"] = float(quote["total_cost"])

        outputs.append({
            "window_id": window,
            "product_id": product,
            "needed_date": need,
            "area": area,
            "quantity_kg": float(q),
            "orders": len(batch),
            "retailer_count": retailer_count,
            "baseline_total": money(baseline),
            "baseline_cost_per_kg": money(baseline / q),
            "baseline_trips": base_trips,
            "baseline_distance_km": float(base_distance),
            "offers": list(quotes.values()),
            "best": best,
            "proposed_offer_id": proposed_offer_id,
            "decision": decision,
            "reason": reason,
            "savings_pct": savings_pct,
            "recommended_savings_pct": recommended_savings_pct,
            "allocated_costs": allocated,
            "evidence_type": (
                "primary"
                if all(
                    o["evidence_type"] == "primary"
                    for o in batch
                )
                else "mixed_or_simulated"
            ),
        })

    return outputs
