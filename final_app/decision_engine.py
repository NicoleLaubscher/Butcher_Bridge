
"""Deterministic procurement evaluator. No network/database dependencies."""

from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP


def D(value):
    return Decimal(str(value))


def money(v):
    return float(
        D(v).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
    )


def validate_order(order):
    """Reject invalid committed demand before procurement evaluation."""

    order_id = order.get("id", "unknown")

    if order.get("retailer_id") in (None, ""):
        raise ValueError(
            f"Order {order_id}: retailer_id is required"
        )

    numeric_fields = (
        "quantity_kg",
        "baseline_price_per_kg",
        "baseline_logistics_cost",
        "baseline_trips",
        "baseline_distance_km",
    )

    for field in numeric_fields:
        try:
            value = D(order[field])
        except (KeyError, TypeError, ValueError, ArithmeticError):
            raise ValueError(
                f"Order {order_id}: invalid {field}"
            ) from None

        if not value.is_finite():
            raise ValueError(
                f"Order {order_id}: {field} must be finite"
            )

        if field == "quantity_kg":
            if value <= 0:
                raise ValueError(
                    f"Order {order_id}: quantity_kg must be positive"
                )
        elif value < 0:
            raise ValueError(
                f"Order {order_id}: {field} cannot be negative"
            )

    trips = D(order["baseline_trips"])

    if trips != trips.to_integral_value():
        raise ValueError(
            f"Order {order_id}: baseline_trips must be a whole number"
        )


def evaluate(orders, offers, tiers, reserved=None, min_fill=0.95, as_of=None):
    """
    Evaluate committed retailer demand against supplier quotations.

    Compatible demand must have the same:
        - Procurement window
        - Product ID (including its database specification)
        - Required delivery date
        - Delivery area

    Supplier offers must satisfy:
        - Available capacity
        - Delivery service area
        - Required lead time
        - Minimum expected fill rate
        - Applicable price tier

    The evaluator compares total delivered procurement costs.

    One supplier must fulfil an entire evaluated batch.

    Important:
        This evaluates already-formed procurement batches.
        It does not perform global optimisation across batches.
    """

    as_of = as_of or date.today()
    reserved = reserved or {}

    groups = defaultdict(list)

    # ---------------------------------------------------------
    # 1. Identify and validate committed retailer demand
    # ---------------------------------------------------------

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

    outputs = []

    # ---------------------------------------------------------
    # 2. Evaluate each compatible procurement batch
    # ---------------------------------------------------------

    for (window, product, need, area), batch in groups.items():

        q = sum(
            D(o["quantity_kg"])
            for o in batch
        )

        baseline = sum(
            D(o["quantity_kg"])
            * D(o["baseline_price_per_kg"])
            + D(o["baseline_logistics_cost"])
            for o in batch
        )

        base_trips = sum(
            int(o["baseline_trips"])
            for o in batch
        )

        base_distance = sum(
            D(o["baseline_distance_km"])
            for o in batch
        )

        ranked = []

        # -----------------------------------------------------
        # 3. Check supplier eligibility and delivered cost
        # -----------------------------------------------------

        for offer in offers:

            if (
                offer["product_id"] != product
                or not offer["active"]
            ):
                continue

            reasons = []

            # Existing reserved quantities in other windows
            reserved_elsewhere = sum(
                D(v)
                for (offer_id, reserved_window), v
                in reserved.items()
                if (
                    offer_id == offer["id"]
                    and reserved_window != window
                )
            )

            available = (
                D(offer["capacity_kg"])
                - reserved_elsewhere
            )

            if available < q:
                reasons.append(
                    "Insufficient unreserved capacity"
                )

            if offer["service_area"].casefold() != area.casefold():
                reasons.append(
                    "Outside service area"
                )

            days_available = (
                date.fromisoformat(need) - as_of
            ).days

            if (
                days_available < 0
                or int(offer["lead_days"]) > days_available
            ):
                reasons.append(
                    "Lead time exceeds required date"
                )

            if D(offer["fill_rate"]) < D(min_fill):
                reasons.append(
                    "Below minimum expected fill rate"
                )

            # Find highest qualifying quantity-price tier
            eligible_tiers = [
                t
                for t in tiers
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
                reasons.append(
                    "No qualifying price tier"
                )

            # Calculate delivered supplier quotation
            total = None

            if best_tier:
                total = (
                    q * D(best_tier["price_per_kg"])
                    + D(offer["fixed_delivery"])
                    + q * D(offer["variable_delivery_per_kg"])
                    + D(offer["handling_cost"])
                )

            ranked.append(
                {
                    "offer_id": offer["id"],
                    "supplier": offer["supplier_name"],
                    "eligible": not reasons,
                    "reasons": reasons,
                    "total_cost": (
                        money(total)
                        if total is not None
                        else None
                    ),
                    "cost_per_kg": (
                        money(total / q)
                        if total is not None
                        else None
                    ),
                    "tier_min_kg": (
                        float(best_tier["min_quantity_kg"])
                        if best_tier
                        else None
                    ),
                    "available_kg": float(available),
                    "delivery_trips": int(
                        offer["coordinated_trips"]
                    ),
                    "distance_km": float(
                        offer["coordinated_distance_km"]
                    ),
                }
            )

        # -----------------------------------------------------
        # 4. Select cheapest feasible supplier
        # -----------------------------------------------------

        feasible = [
            v
            for v in ranked
            if v["eligible"]
        ]

        winner = (
            min(
                feasible,
                key=lambda x: x["total_cost"],
            )
            if feasible
            else None
        )

        # Count distinct participating retailers, not orders
        retailer_count = len(
            {
                o["retailer_id"]
                for o in batch
            }
        )

        # -----------------------------------------------------
        # 5. Determine procurement recommendation
        # -----------------------------------------------------

        if not winner:

            decision = "REJECT_NO_FEASIBLE_SUPPLIER"

            reason = (
                "No eligible supplier satisfies the procurement "
                "requirements. Retailers should retain their "
                "existing procurement arrangements."
            )

        elif retailer_count == 1:

            if D(winner["total_cost"]) < baseline:

                decision = "INDIVIDUAL_BETTER_QUOTE"

                reason = (
                    "Only one retailer is participating. A cheaper "
                    "feasible supplier quotation is available. "
                    "Recommend individual procurement from this "
                    "supplier. This is not aggregation."
                )

            else:

                decision = "INDIVIDUAL_KEEP_BASELINE"

                reason = (
                    "Only one retailer is participating. The retailer "
                    "should retain its existing procurement arrangement "
                    "because it is cheaper than or equal in cost to the "
                    "alternative supplier quotation. "
                    "This is not aggregation."
                )

        elif D(winner["total_cost"]) >= baseline:

            decision = "REJECT_NOT_CHEAPER"

            reason = (
                "Multi-retailer aggregation does not reduce total "
                "delivered procurement cost. Retailers should retain "
                "their existing procurement arrangements."
            )

        else:

            decision = "ACCEPT"

            reason = (
                "Genuine multi-retailer aggregation is feasible and "
                "lowers total delivered procurement cost compared "
                "with existing arrangements."
            )

        # -----------------------------------------------------
        # 6. Calculate supplier group cost
        # -----------------------------------------------------

        group_cost = (
            D(winner["total_cost"])
            if winner
            else None
        )

        # -----------------------------------------------------
        # 7. Allocate supplier quotation across orders
        # -----------------------------------------------------

        allocated = []

        if winner:

            shares = []

            for o in batch[:-1]:

                shares.append(
                    D(
                        str(
                            money(
                                group_cost
                                * D(o["quantity_kg"])
                                / q
                            )
                        )
                    )
                )

            # Final share absorbs rounding difference
            shares.append(
                group_cost - sum(shares)
            )

            allocated = [
                {
                    "order_id": o["id"],
                    "retailer": o["retailer_name"],
                    "allocated_cost": money(c),
                }
                for o, c in zip(batch, shares)
            ]

        # -----------------------------------------------------
        # 8. Calculate raw supplier quote savings
        # -----------------------------------------------------

        savings_pct = (
            money(
                (baseline - group_cost)
                / baseline
                * 100
            )
            if (
                group_cost is not None
                and baseline > 0
            )
            else None
        )

        # -----------------------------------------------------
        # 9. Calculate savings for recommended procurement
        # -----------------------------------------------------

        recommended_savings_pct = (
            money(
                (baseline - group_cost)
                / baseline
                * 100
            )
            if (
                decision in (
                    "ACCEPT",
                    "INDIVIDUAL_BETTER_QUOTE",
                )
                and group_cost is not None
                and baseline > 0
            )
            else 0.0
        )

        # -----------------------------------------------------
        # 10. Return batch evaluation for dashboard
        # -----------------------------------------------------

        outputs.append(
            {
                "window_id": window,
                "product_id": product,
                "needed_date": need,
                "area": area,
                "quantity_kg": float(q),
                "orders": len(batch),
                "retailer_count": retailer_count,
                "baseline_total": money(baseline),
                "baseline_cost_per_kg": money(
                    baseline / q
                ),
                "baseline_trips": base_trips,
                "baseline_distance_km": float(
                    base_distance
                ),
                "offers": ranked,
                "best": winner,
                "decision": decision,
                "reason": reason,
                "savings_pct": savings_pct,
                "recommended_savings_pct": (
                    recommended_savings_pct
                ),
                "allocated_costs": allocated,
                "evidence_type": (
                    "primary"
                    if all(
                        o["evidence_type"] == "primary"
                        for o in batch
                    )
                    else "mixed_or_simulated"
                ),
            }
        )

    return outputs
