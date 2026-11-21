
"""Deterministic procurement evaluator; no database or network dependencies."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP
from fractions import Fraction
from itertools import combinations

if __package__:
    from .group_formation_planner import GroupOffer, GroupPlanningLimit, GroupPlanningLimits, plan_groups
    from .joint_capacity_planner import plan_offers
else:
    from group_formation_planner import GroupOffer, GroupPlanningLimit, GroupPlanningLimits, plan_groups
    from joint_capacity_planner import plan_offers


def D(value):
    return Decimal(str(value))


def _round_money(value):
    return D(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def money(value):
    return float(_round_money(value))


def _order_baseline(order):
    return (
        D(order["quantity_kg"]) * D(order["baseline_price_per_kg"])
        + D(order["baseline_logistics_cost"])
    )


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


def _apportion_cents(total_cents, weights):
    """Divide whole cents by exact weights, with ascending IDs breaking ties."""
    if total_cents == 0:
        return dict.fromkeys(weights, 0)

    total_weight = sum(weights.values())
    shares = {}
    remainders = {}
    for identifier, weight in weights.items():
        shares[identifier], remainders[identifier] = divmod(total_cents * weight, total_weight)

    remaining = total_cents - sum(shares.values())
    remainder_order = sorted(
        remainders, key=lambda identifier: (-remainders[identifier], identifier),
    )
    for identifier in remainder_order[:remaining]:
        shares[identifier] += 1
    return shares


def _quantity_weights(orders):
    return {order["id"]: Fraction(D(order["quantity_kg"])) for order in orders}


def _from_cents(cents):
    return Decimal(cents).scaleb(-2)


def _allocate_proposed_costs(total_cents, batch, retailer_caps):
    retailer_cents = _apportion_cents(total_cents, retailer_caps)
    orders_by_retailer = defaultdict(list)
    for order in batch:
        orders_by_retailer[order["retailer_id"]].append(order)

    retailer_costs = []
    order_costs = {}
    for retailer_id, orders in sorted(orders_by_retailer.items()):
        charge = retailer_cents[retailer_id]
        order_cents = _apportion_cents(charge, _quantity_weights(orders))
        order_costs.update(order_cents)
        retailer_costs.append({
            "retailer_id": retailer_id,
            "retailer": orders[0]["retailer_name"],
            "baseline_cap": format(_from_cents(retailer_caps[retailer_id]), "f"),
            "proposed_cost": format(_from_cents(charge), "f"),
            "orders": [
                {"order_id": order_id, "proposed_cost": format(_from_cents(cents), "f")}
                for order_id, cents in sorted(order_cents.items())
            ],
        })
    return retailer_costs, order_costs


def evaluate(orders, offers, tiers, reserved=None, min_fill=0.95, as_of=None):
    """Evaluate batches using the capacity holds supplied by the caller."""
    batches, _ = _evaluate(orders, offers, tiers, reserved, min_fill, as_of)
    return batches


def _allocation_state(allocations):
    reserved = {}
    allocation_statuses = {}
    for allocation in allocations:
        key = (allocation["offer_id"], allocation["window_id"])
        status = allocation["status"]
        if key in allocation_statuses:
            raise ValueError(
                "Multiple allocation rows share an offer and window. "
                "Review reservations before planning."
            )
        if status not in ("reserved", "released"):
            raise ValueError("Unrecognised allocation status. Review reservations before planning.")
        allocation_statuses[key] = status
        if status == "reserved":
            reserved[key] = allocation["quantity_kg"]

    return reserved, allocation_statuses


def evaluate_plan(orders, offers, tiers, allocations, min_fill=0.95, as_of=None, *,
                  comparison_details=False):
    """Return fixed-batch decisions and Decimal proposal totals for fresh keys."""
    reserved, allocation_statuses = _allocation_state(allocations)
    return _evaluate(
        orders, offers, tiers, reserved, min_fill, as_of,
        allocation_statuses=allocation_statuses, comparison_details=comparison_details,
    )


def evaluate_optimised_plan(orders, offers, tiers, allocations, min_fill=0.95,
                            as_of=None, *, limits=GroupPlanningLimits(),
                            comparison_details=False):
    """Return an exact retailer-group plan or a separately evaluated fixed plan."""
    orders, offers, tiers, allocations = map(tuple, (orders, offers, tiers, allocations))
    as_of = as_of or date.today()
    groups = _group_orders(orders)
    order_ids = _committed_order_ids(orders)

    reserved, statuses = _allocation_state(allocations)
    evaluator = _QuoteEvaluator(offers, tiers, reserved, min_fill, as_of, statuses)
    try:
        batches, plan = _optimised_groups(groups, evaluator, limits)
    except GroupPlanningLimit as limit:
        items, totals = evaluate_plan(
            orders, offers, tiers, allocations, min_fill, as_of,
            comparison_details=comparison_details,
        )
        if not comparison_details:
            for item in items:
                key = (item["window_id"], item["product_id"], item["needed_date"], item["area"])
                item.update(_group_details(key, groups[key], item["proposed_offer_id"]))
        reason = str(limit)
        if any(item["decision"] == "REJECT_PLANNING_LIMIT" for item in items):
            reason += " The fixed-batch planner also reached its limit and kept the baselines."
        planning = {"planning_status": "fallback", "fallback_reason": reason}
    else:
        items, totals = _render_plan(
            batches, plan, optimised=True, comparison_details=comparison_details,
        )
        planning = {"planning_status": "exact", "fallback_reason": None}

    _verify_order_coverage(items, order_ids)
    return items, totals, planning


def _committed_order_ids(orders):
    order_ids = set()
    for order in orders:
        if order["status"] != "committed":
            continue
        order_id = order.get("id")
        if order_id in (None, ""):
            raise ValueError("An order ID is required for each committed order.")
        if order_id in order_ids:
            raise ValueError("Duplicate committed order IDs cannot be planned.")
        order_ids.add(order_id)
    return order_ids


def _verify_order_coverage(items, order_ids):
    covered = [order_id for item in items for order_id in item["order_ids"]]
    if len(covered) != len(order_ids) or set(covered) != order_ids:
        raise RuntimeError("The plan did not cover each committed order exactly once.")


def _savings_percentage(savings, denominator):
    if not denominator:
        return None
    return format(_round_money(savings * 100 / denominator), "f")


def _plan_summary(baseline, total_cost, fallback_reason):
    savings = baseline - total_cost
    return {
        "total_cost": format(total_cost, "f"),
        "savings_vs_baseline": format(savings, "f"),
        "savings_pct_of_baseline": _savings_percentage(savings, baseline),
        "planning_status": "fallback" if fallback_reason is not None else "exact",
        "fallback_reason": fallback_reason,
    }


def _supplier_assignments(items):
    return {
        (item["proposed_offer_id"], tuple(item["order_ids"]))
        for item in items if item["proposed_offer_id"] is not None
    }


def compare_plans(orders, offers, tiers, allocations, min_fill=0.95, as_of=None, *,
                  limits=GroupPlanningLimits()):
    """Compare both plans on one snapshot, including exact costs and membership."""
    orders, offers, tiers, allocations = map(tuple, (orders, offers, tiers, allocations))
    as_of = as_of or date.today()
    order_ids = _committed_order_ids(orders)
    fixed, _ = evaluate_plan(
        orders, offers, tiers, allocations, min_fill, as_of=as_of, comparison_details=True,
    )
    optimised, _, planning = evaluate_optimised_plan(
        orders, offers, tiers, allocations, min_fill, as_of=as_of, limits=limits,
        comparison_details=True,
    )
    _verify_order_coverage(fixed, order_ids)
    _verify_order_coverage(optimised, order_ids)
    baseline = sum((_order_baseline(o) for o in orders if o["status"] == "committed"), Decimal(0))
    fixed_cost = sum((item["planned_cost"] for item in fixed), Decimal(0))
    optimised_cost = sum((item["planned_cost"] for item in optimised), Decimal(0))
    fixed_fallback = next(
        (item["reason"] for item in fixed if item["decision"] == "REJECT_PLANNING_LIMIT"), None,
    )
    incremental = fixed_cost - optimised_cost
    summary = {
        "evaluated_on": as_of.isoformat(),
        "committed_order_count": len(order_ids),
        "baseline_total": format(baseline, "f"),
        "fixed": _plan_summary(baseline, fixed_cost, fixed_fallback),
        "optimised": _plan_summary(baseline, optimised_cost, planning["fallback_reason"]),
        "incremental": {
            "savings_vs_fixed": format(incremental, "f"),
            "savings_pct_of_fixed": _savings_percentage(incremental, fixed_cost),
        },
        "same_cost": fixed_cost == optimised_cost,
        # With identical order coverage, unchanged supplier assignments imply
        # unchanged individual baselines even if their displayed rows differ.
        "same_assignments": _supplier_assignments(fixed) == _supplier_assignments(optimised),
    }
    return summary, {"fixed": fixed, "optimised": optimised}


def _group_orders(orders):
    groups = defaultdict(list)
    for order in orders:
        if order["status"] != "committed":
            continue
        validate_order(order)
        key = (
            order["window_id"],
            order["product_id"],
            str(order["needed_date"]),
            order["delivery_area"],
        )
        groups[key].append(order)
    return groups


@dataclass
class _QuotedBatch:
    key: tuple
    orders: list
    quantity: Decimal
    baseline: Decimal
    quotes: dict
    candidates: list
    retailer_caps: dict
    savings: dict


class _QuoteEvaluator:
    def __init__(self, offers, tiers, reserved, min_fill, as_of, allocation_statuses):
        self.as_of = as_of or date.today()
        self.allocation_statuses = allocation_statuses
        validate_supplier_inputs(offers, tiers, reserved, min_fill)
        self.min_fill = D(min_fill)

        self.reserved_by_offer = defaultdict(Decimal)
        for (offer_id, _window_id), quantity in reserved.items():
            self.reserved_by_offer[offer_id] += D(quantity)

        self.available_by_offer = {}
        self.offers_by_product = defaultdict(list)
        for offer in sorted(offers, key=lambda row: row["id"]):
            offer_id = offer["id"]
            self.available_by_offer[offer_id] = D(offer["capacity_kg"]) - self.reserved_by_offer[offer_id]
            if offer["active"]:
                self.offers_by_product[offer["product_id"]].append(offer)

        self.tiers_by_offer = defaultdict(list)
        for tier in tiers:
            self.tiers_by_offer[tier["offer_id"]].append(tier)

    def quote(self, key, batch):
        window, product, need, area = key
        batch = sorted(batch, key=lambda order: order["id"], reverse=True)
        q = sum(D(o["quantity_kg"]) for o in batch)

        retailer_baselines = defaultdict(Decimal)
        for order in batch:
            retailer_baselines[order["retailer_id"]] += _order_baseline(order)
        baseline = sum(retailer_baselines.values())
        retailer_caps = {
            retailer_id: int(amount.scaleb(2).to_integral_value(rounding=ROUND_FLOOR))
            for retailer_id, amount in retailer_baselines.items()
        }
        max_recoverable_cost = _from_cents(sum(retailer_caps.values()))

        quotes = {}

        for offer in self.offers_by_product.get(product, ()):
            reasons = []

            available = self.available_by_offer[offer["id"]]

            if available < q:
                reasons.append("Insufficient unreserved capacity")

            if offer["service_area"].casefold() != area.casefold():
                reasons.append("Outside service area")

            days_available = (date.fromisoformat(need) - self.as_of).days

            if (
                days_available < 0
                or int(offer["lead_days"]) > days_available
            ):
                reasons.append("Lead time exceeds required date")

            if D(offer["fill_rate"]) < self.min_fill:
                reasons.append("Below minimum expected fill rate")

            eligible_tiers = [
                t for t in self.tiers_by_offer.get(offer["id"], ())
                if D(t["min_quantity_kg"]) <= q
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

            quote_cost = _round_money(total) if total is not None else None
            cost_sharing_reason = None
            if quote_cost is not None and max_recoverable_cost < quote_cost < baseline:
                cost_sharing_reason = (
                    "The quote is cheaper than the combined baseline. Its cost cannot be "
                    "shared in whole cents within each retailer's baseline."
                )

            quotes[offer["id"]] = {
                "offer_id": offer["id"],
                "supplier": offer["supplier_name"],
                "eligible": not reasons,
                "reasons": reasons,
                "total_cost": quote_cost,
                "cost_sharing_reason": cost_sharing_reason,
                "cost_per_kg": (
                    money(total / q) if total is not None else None
                ),
                "tier_min_kg": (
                    float(best_tier["min_quantity_kg"])
                    if best_tier else None
                ),
                "reserved_kg": float(self.reserved_by_offer[offer["id"]]),
                "available_kg": float(available),
                "reservation_key_status": (
                    self.allocation_statuses.get((offer["id"], window), "free")
                    if self.allocation_statuses is not None else None
                ),
                "delivery_trips": int(offer["coordinated_trips"]),
                "distance_km": float(offer["coordinated_distance_km"]),
            }

        candidates = [
            quote for quote in quotes.values()
            if quote["eligible"] and quote["reservation_key_status"] in (None, "free")
        ]
        savings = {
            quote["offer_id"]: baseline - quote["total_cost"]
            for quote in candidates
            if quote["total_cost"] < baseline and quote["cost_sharing_reason"] is None
        }
        return _QuotedBatch(key, batch, q, baseline, quotes, candidates, retailer_caps, savings)


def _optimised_groups(groups, evaluator, limits):
    buckets = []
    quote_evaluations = 0
    for key, orders in sorted(groups.items()):
        by_retailer = defaultdict(list)
        for order in orders:
            by_retailer[order["retailer_id"]].append(order)
        bundles = [bundle for _, bundle in sorted(by_retailer.items())]
        if len(bundles) > limits.max_retailers_per_bucket:
            raise GroupPlanningLimit(
                f"The retailer bundle limit of {limits.max_retailers_per_bucket:,} "
                "per compatibility bucket was exceeded."
            )

        offer_count = len(evaluator.offers_by_product.get(key[1], ()))
        if offer_count:
            quote_evaluations += ((1 << len(bundles)) - 1) * offer_count
        if quote_evaluations > limits.max_quote_evaluations:
            raise GroupPlanningLimit(
                f"The group-offer evaluation limit of {limits.max_quote_evaluations:,} was exceeded."
            )
        buckets.append((key, bundles, offer_count))

    quoted_groups = {}
    candidates = []
    decisions = []
    next_bundle = 0
    for key, bundles, offer_count in buckets:
        if not offer_count:
            decisions.extend((evaluator.quote(key, bundle), None) for bundle in bundles)
            continue
        indexed = [(1 << index, bundle) for index, bundle in enumerate(bundles, next_bundle)]
        next_bundle += len(bundles)
        for size in range(1, len(bundles) + 1):
            for group in combinations(indexed, size):
                mask = sum(bit for bit, _ in group)
                batch = evaluator.quote(key, [order for _, bundle in group for order in bundle])
                quoted_groups[mask] = batch
                candidates.extend(
                    GroupOffer(mask, offer_id, batch.quantity, savings)
                    for offer_id, savings in batch.savings.items()
                )

    selected = plan_groups(candidates, evaluator.available_by_offer, limits.max_search_nodes)
    assigned_offers = {option.members: option.offer_id for option in selected}
    assigned_members = sum(assigned_offers)  # Selected masks are disjoint.
    for mask, batch in quoted_groups.items():
        if mask in assigned_offers or (mask.bit_count() == 1 and not (mask & assigned_members)):
            decisions.append((batch, assigned_offers.get(mask)))
    decisions.sort(key=lambda pair: (pair[0].key, tuple(sorted(pair[0].retailer_caps))))

    batches = [batch for batch, _ in decisions]
    plan = {index: offer_id for index, (_, offer_id) in enumerate(decisions) if offer_id is not None}
    return batches, plan


def _group_details(key, orders, proposed_offer_id):
    window, product, need, area = key
    order_ids = sorted(order["id"] for order in orders)
    return {
        "group_id": "orders-" + "-".join(map(str, order_ids)),
        "retailer_ids": sorted({order["retailer_id"] for order in orders}),
        "order_ids": order_ids,
        "source_bucket": {
            "window_id": window, "product_id": product, "needed_date": need, "delivery_area": area,
        },
        "procurement": "supplier" if proposed_offer_id is not None else "baseline",
    }


def _retailer_memberships(orders):
    members = {}
    for order in sorted(orders, key=lambda row: (row["retailer_id"], row["id"])):
        retailer_id = order["retailer_id"]
        if retailer_id not in members:
            members[retailer_id] = {
                "retailer_id": retailer_id,
                "name": order["retailer_name"],
                "order_ids": [],
                "baseline": Decimal(0),
            }
        member = members[retailer_id]
        member["order_ids"].append(order["id"])
        member["baseline"] += _order_baseline(order)
    return list(members.values())


def _evaluate(orders, offers, tiers, reserved, min_fill, as_of, *, allocation_statuses=None,
              comparison_details=False):
    evaluator = _QuoteEvaluator(offers, tiers, reserved or {}, min_fill, as_of, allocation_statuses)
    groups = _group_orders(orders)
    batches = [evaluator.quote(key, group) for key, group in sorted(groups.items())]
    plan = plan_offers([(batch.quantity, batch.savings) for batch in batches],
                       evaluator.available_by_offer)
    return _render_plan(batches, plan, comparison_details=comparison_details)


def _render_plan(batches, plan, *, optimised=False, comparison_details=False):
    outputs = []
    proposed_totals = defaultdict(Decimal)
    for index, quoted in enumerate(batches):
        window, product, need, area = quoted.key
        batch, q, baseline = quoted.orders, quoted.quantity, quoted.baseline
        quotes, candidates = quoted.quotes, quoted.candidates
        retailer_caps, savings = quoted.retailer_caps, quoted.savings
        proposed_offer_id = plan.get(index) if plan is not None else None
        base_trips = sum(int(o["baseline_trips"]) for o in batch)
        base_distance = sum(D(o["baseline_distance_km"]) for o in batch)

        retailer_count = len(retailer_caps)

        if proposed_offer_id is not None:
            best = quotes[proposed_offer_id]
            proposed_totals[(proposed_offer_id, window)] += q
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

        elif optimised:
            best = None
            decision = "INDIVIDUAL_KEEP_BASELINE"
            reason = "The optimised plan retains this retailer's individual procurement baseline."

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
                candidates,
                key=lambda quote: quote["total_cost"],
                default=None,
            )
            if best is None:
                decision = "REJECT_NO_FEASIBLE_SUPPLIER"
                if any(quote["eligible"] for quote in quotes.values()):
                    reason = (
                        "The eligible quotes already have allocation rows for this "
                        "window. Review the existing reservations before booking."
                    )
                else:
                    reason = (
                        "No eligible supplier satisfies the procurement "
                        "requirements. Retailers should retain their "
                        "existing procurement arrangements."
                    )
            elif best["cost_sharing_reason"] is not None:
                decision = "REJECT_NOT_CHEAPER"
                reason = best["cost_sharing_reason"] + " Keep the individual procurement baselines."
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
        proposed_retailer_costs = []

        if group_cost is not None:
            total_cents = int(group_cost.scaleb(2))
            if proposed_offer_id is not None:
                proposed_retailer_costs, order_cents = _allocate_proposed_costs(
                    total_cents, batch, retailer_caps,
                )
            else:
                order_cents = _apportion_cents(total_cents, _quantity_weights(batch))
            allocated = [
                {
                    "order_id": o["id"],
                    "retailer": o["retailer_name"],
                    "allocated_cost": float(_from_cents(order_cents[o["id"]])),
                }
                for o in batch
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

        row = {
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
            "proposed_retailer_costs": proposed_retailer_costs,
            "evidence_type": (
                "primary"
                if all(
                    o["evidence_type"] == "primary"
                    for o in batch
                )
                else "mixed_or_simulated"
            ),
        }
        if optimised or comparison_details:
            row.update(_group_details(quoted.key, batch, proposed_offer_id))
        if comparison_details:
            row["planned_cost"] = group_cost if proposed_offer_id is not None else baseline
            row["retailers"] = _retailer_memberships(batch)
        outputs.append(row)

    return outputs, dict(proposed_totals)
