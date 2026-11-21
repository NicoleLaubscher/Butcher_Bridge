"""Run two simulated procurement comparisons offline with the production planners."""

from collections import defaultdict
from datetime import date
from decimal import Decimal

if __package__:
    from .decision_engine import compare_plans
else:
    from decision_engine import compare_plans


EVALUATED_ON = date(2026, 11, 19)


def _scenario(baseline_prices, offer_specs):
    orders = [
        {
            "id": retailer_id,
            "retailer_id": retailer_id,
            "retailer_name": f"Retailer {name}",
            "window_id": 1,
            "product_id": 1,
            "needed_date": date(2026, 12, 8),
            "delivery_area": "Soweto",
            "quantity_kg": 100,
            "baseline_price_per_kg": baseline_price,
            "baseline_logistics_cost": 0,
            "baseline_trips": 1,
            "baseline_distance_km": 0,
            "status": "committed",
            "evidence_type": "simulated",
        }
        for retailer_id, (name, baseline_price) in enumerate(zip("ABCD", baseline_prices), 1)
    ]
    offers = []
    tiers = []
    for offer_id, (capacity, delivery, thresholds) in enumerate(offer_specs, 1):
        offers.append({
            "id": offer_id,
            "product_id": 1,
            "supplier_name": f"Offer {offer_id}",
            "capacity_kg": capacity,
            "lead_days": 3,
            "fill_rate": Decimal("0.98"),
            "service_area": "Soweto",
            "fixed_delivery": delivery,
            "variable_delivery_per_kg": 0,
            "handling_cost": 0,
            "coordinated_trips": 1,
            "coordinated_distance_km": 0,
            "active": True,
        })
        tiers.extend(
            {"offer_id": offer_id, "min_quantity_kg": kg, "price_per_kg": price}
            for kg, price in thresholds
        )
    allocations = [{"offer_id": 1, "window_id": 2, "quantity_kg": 50, "status": "reserved"}]
    return orders, offers, tiers, allocations


def scenario_one():
    return _scenario((120, 120, 60), [(350, 600, [(1, 105), (200, 90), (300, 88)])])


def scenario_two():
    return _scenario(
        (120, 120, 120, 120),
        [(250, 500, [(1, 100), (200, 80)]), (400, 600, [(1, 105), (200, 92), (400, 90)])],
    )


def _print_plan(rows, orders_by_id, offers, reserved):
    proposed_kg = defaultdict(Decimal)
    for row in rows:
        offer_id = row["proposed_offer_id"]
        if offer_id is None:
            assignment = "Individual baseline procurement"
        else:
            assignment = f"{row['best']['supplier']} in window {row['window_id']}"
            proposed_kg[offer_id] += sum(orders_by_id[order_id]["quantity_kg"] for order_id in row["order_ids"])
        print(f"  {assignment} | orders {row['order_ids']} | R{row['planned_cost']:.2f}")
        shares = {share["retailer_id"]: share for share in row["proposed_retailer_costs"]}
        for member in row["retailers"]:
            baseline = member["baseline"]
            charge = cap = baseline
            if offer_id is not None:
                share = shares[member["retailer_id"]]
                charge = Decimal(share["proposed_cost"])
                cap = Decimal(share["baseline_cap"])
            fair = "PASS" if 0 <= charge <= cap <= baseline else "FAIL"
            print(f"    {member['name']} | orders {member['order_ids']} | cost R{charge:.2f} "
                  f"| baseline R{baseline:.2f} | estimated saving R{baseline - charge:.2f} | fairness {fair}")
    for offer in offers:
        offer_id = offer["id"]
        proposed = proposed_kg[offer_id]
        existing = reserved[offer_id]
        capacity = offer["capacity_kg"]
        check = "PASS" if existing + proposed <= capacity else "FAIL"
        print(f"  {offer['supplier_name']} capacity | {existing} kg reserved + {proposed} kg proposed "
              f"of {capacity} kg | {check}")


def main():
    for number, scenario in enumerate((scenario_one, scenario_two), 1):
        orders, offers, tiers, allocations = scenario()
        summary, plans = compare_plans(orders, offers, tiers, allocations, as_of=EVALUATED_ON)
        print(f"\nSIMULATED scenario {number} | evaluated {summary['evaluated_on']} | estimated costs and savings")
        print(f"Individual procurement baseline R{Decimal(summary['baseline_total']):.2f}")
        reserved = defaultdict(Decimal)
        for hold in allocations:
            if hold["status"] == "reserved":
                reserved[hold["offer_id"]] += hold["quantity_kg"]
        for offer in offers:
            price_tiers = ", ".join(
                f"{tier['min_quantity_kg']} kg at R{tier['price_per_kg']}/kg"
                for tier in tiers if tier["offer_id"] == offer["id"]
            )
            capacity = offer["capacity_kg"]
            print(f"{offer['supplier_name']} | {capacity - reserved[offer['id']]} of {capacity} kg unreserved "
                  f"| fixed delivery R{offer['fixed_delivery']} per purchase | tiers {price_tiers}")
        orders_by_id = {order["id"]: order for order in orders}
        for mode, rows in plans.items():
            result = summary[mode]
            print(f"{mode.title()} plan | {result['planning_status']} | cost R{Decimal(result['total_cost']):.2f} "
                  f"| estimated savings R{Decimal(result['savings_vs_baseline']):.2f} "
                  f"({result['savings_pct_of_baseline']}% of baseline)")
            if result["fallback_reason"]:
                print(result["fallback_reason"])
            _print_plan(rows, orders_by_id, offers, reserved)
        incremental = summary["incremental"]
        print(f"Incremental estimated savings R{Decimal(incremental['savings_vs_fixed']):.2f} "
              f"({incremental['savings_pct_of_fixed']}% of fixed plan cost)")


if __name__ == "__main__":
    main()
