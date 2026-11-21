"""Retailer-group optimisation tests using simulated orders and offers."""

import unittest
from decimal import Decimal
from itertools import combinations
from random import Random

from decision_engine import evaluate_optimised_plan, evaluate_plan
from group_formation_planner import GroupOffer, GroupPlanningLimits, plan_groups
from test_decision_engine import TODAY, offer, order, tiers


def supplier(offer_id, capacity, fixed_delivery):
    row = offer(offer_id, capacity=capacity, fixed=fixed_delivery)
    row.update(variable_delivery_per_kg=0, handling_cost=0)
    return row


def price_tiers(offer_id, thresholds):
    return [dict(offer_id=offer_id, min_quantity_kg=kg, price_per_kg=price)
            for kg, price in thresholds]


def subset_scenario():
    orders = [order(1, 40, baseline=120, logistics=0, retailer_id=1),
              order(2, 60, baseline=120, logistics=0, retailer_id=1),
              order(3, 100, baseline=120, logistics=0, retailer_id=2),
              order(4, 100, baseline=60, logistics=0, retailer_id=3)]
    offers = [supplier(1, 350, 600)]
    prices = price_tiers(1, [(1, 105), (200, 90), (300, 88)])
    holds = [dict(offer_id=1, window_id=2, quantity_kg=50, status="reserved")]
    return orders, offers, prices, holds


class TestGroupFormation(unittest.TestCase):
    def assert_coverage(self, rows, order_ids):
        self.assertEqual(sorted(order_id for row in rows for order_id in row["order_ids"]),
                         sorted(order_ids))
        self.assertEqual(len({row["group_id"] for row in rows}), len(rows))

    def test_subset_and_baseline_improve_on_the_full_batch(self):
        inputs = subset_scenario()
        fixed, _ = evaluate_plan(*inputs, as_of=TODAY)
        rows, totals, planning = evaluate_optimised_plan(*inputs, as_of=TODAY)

        self.assertEqual(fixed[0]["best"]["total_cost"], 27000)
        self.assertEqual(planning, {"planning_status": "exact", "fallback_reason": None})
        group, baseline = rows
        self.assertEqual(group["decision"], "ACCEPT")
        self.assertEqual(group["retailer_ids"], [1, 2])
        self.assertEqual(group["order_ids"], [1, 2, 3])
        self.assertEqual(group["source_bucket"], {
            "window_id": 1, "product_id": 1, "needed_date": "2026-12-08", "delivery_area": "Soweto",
        })
        self.assertEqual(group["best"]["total_cost"], 18600)
        self.assertEqual([row["proposed_cost"] for row in group["proposed_retailer_costs"]],
                         ["9300.00", "9300.00"])
        self.assertEqual(group["proposed_retailer_costs"][0]["orders"], [
            {"order_id": 1, "proposed_cost": "3720.00"}, {"order_id": 2, "proposed_cost": "5580.00"},
        ])
        self.assertEqual(baseline["retailer_ids"], [3])
        self.assertEqual(baseline["procurement"], "baseline")
        self.assertEqual(baseline["baseline_total"], 6000)
        self.assertIsNone(baseline["proposed_offer_id"])
        self.assertEqual(baseline["proposed_retailer_costs"], [])
        self.assertEqual(totals, {(1, 1): Decimal(200)})
        self.assert_coverage(rows, [1, 2, 3, 4])

    def test_two_groups_save_even_with_two_delivery_charges(self):
        orders = [order(i, 100, baseline=120, logistics=0) for i in range(1, 5)]
        offers = [supplier(1, 250, 500), supplier(2, 400, 600)]
        prices = price_tiers(1, [(1, 100), (200, 80)]) + price_tiers(2, [(1, 105), (200, 92), (400, 90)])
        holds = [dict(offer_id=1, window_id=2, quantity_kg=50, status="reserved")]

        fixed, _ = evaluate_plan(orders, offers, prices, holds, as_of=TODAY)
        rows, totals, planning = evaluate_optimised_plan(orders, offers, prices, holds, as_of=TODAY)

        self.assertEqual(planning["planning_status"], "exact")
        self.assertEqual(fixed[0]["best"]["total_cost"], 36600)
        self.assertEqual([row["proposed_offer_id"] for row in rows], [1, 2])
        self.assertEqual([row["best"]["total_cost"] for row in rows], [16500, 19000])
        self.assertEqual([[share["proposed_cost"] for share in row["proposed_retailer_costs"]]
                          for row in rows], [["8250.00", "8250.00"], ["9500.00", "9500.00"]])
        self.assertEqual(totals, {(1, 1): Decimal(200), (2, 1): Decimal(200)})
        self.assert_coverage(rows, [1, 2, 3, 4])

    def test_an_indivisible_bundle_can_keep_its_baseline_while_another_buys_alone(self):
        orders = [order(1, 100, retailer_id=1), order(2, 100, retailer_id=1),
                  order(3, 100, retailer_id=2), order(4, 100, status="withdrawn")]

        rows, totals, _ = evaluate_optimised_plan(orders, [offer(1, capacity=150)], tiers(), [], as_of=TODAY)

        self.assertEqual([row["decision"] for row in rows], ["INDIVIDUAL_KEEP_BASELINE", "INDIVIDUAL_BETTER_QUOTE"])
        self.assertEqual([row["order_ids"] for row in rows], [[1, 2], [3]])
        self.assertEqual(totals, {(1, 1): Decimal(100)})
        self.assert_coverage(rows, [1, 2, 3])

    def test_one_plan_can_combine_groups_single_purchases_and_baselines(self):
        orders, offers, prices, holds = subset_scenario()
        orders.append(order(5, Decimal("100.00"), baseline=120, logistics=0,
                            needed_date="2026-12-09"))

        rows, totals, _ = evaluate_optimised_plan(orders, offers, prices, holds, as_of=TODAY)

        self.assertEqual([row["decision"] for row in rows],
                         ["ACCEPT", "INDIVIDUAL_KEEP_BASELINE", "INDIVIDUAL_BETTER_QUOTE"])
        self.assertEqual([row["proposed_offer_id"] for row in rows], [1, None, 1])
        self.assertEqual(totals, {(1, 1): Decimal("300.00")})
        self.assert_coverage(rows, [1, 2, 3, 4, 5])

    def test_same_retailer_in_distinct_compatibility_buckets_is_planned_separately(self):
        orders = [order(1, 100, retailer_id=1), order(2, 100, retailer_id=1, window=2),
                  order(3, 100, retailer_id=1, needed_date="2026-12-09"), order(4, 100, area="soweto")]
        orders.append(dict(order(5, 100), product_id=2))

        rows, _, planning = evaluate_optimised_plan(orders, [offer(1)], tiers(), [], as_of=TODAY)

        self.assertEqual(planning["planning_status"], "exact")
        self.assertEqual(sorted(row["order_ids"] for row in rows), [[1], [2], [3], [4], [5]])
        self.assertEqual(next(row for row in rows if row["order_ids"] == [5])["procurement"], "baseline")
        self.assert_coverage(rows, [1, 2, 3, 4, 5])

    def test_offer_capacity_is_shared_and_both_allocation_statuses_occupy_keys(self):
        orders = [order(1, Decimal("100.10"), baseline=120, logistics=0),
                  order(2, Decimal("100.20"), baseline=120, logistics=0),
                  order(3, Decimal("200.30"), window=2, baseline=110, logistics=0),
                  order(4, 100, window=3, baseline=200), order(5, 100, window=4, baseline=200)]
        holds = [dict(offer_id=1, window_id=3, quantity_kg=Decimal("50.00"), status="reserved"),
                 dict(offer_id=1, window_id=4, quantity_kg=Decimal("5.00"), status="released")]

        rows, totals, _ = evaluate_optimised_plan(
            orders, [supplier(1, Decimal("250.30"), 600)], tiers(), holds, as_of=TODAY,
        )

        self.assertEqual([row["order_ids"] for row in rows], [[1, 2], [3], [4], [5]])
        self.assertEqual([row["proposed_offer_id"] for row in rows], [1, None, None, None])
        self.assertEqual([row["offers"][0]["reservation_key_status"] for row in rows],
                         ["free", "free", "reserved", "released"])
        self.assertTrue(all(row["offers"][0]["available_kg"] == 200.30 for row in rows))
        self.assertEqual(totals, {(1, 1): Decimal("200.30")})
        self.assert_coverage(rows, [1, 2, 3, 4, 5])

    def test_reservation_total_combines_same_key_purchases_with_separate_prices(self):
        orders = [order(1, Decimal("0.10"), baseline=100, logistics=0),
                  order(2, Decimal("0.20"), baseline=100, logistics=0, needed_date="2026-12-09")]
        prices = price_tiers(1, [(Decimal("0.01"), 82), (Decimal("0.20"), 80)])

        rows, totals, _ = evaluate_optimised_plan(
            orders, [supplier(1, Decimal("0.30"), 1)], prices, [], as_of=TODAY,
        )

        self.assertEqual([row["best"]["total_cost"] for row in rows], [9.20, 17.00])
        self.assertEqual(totals, {(1, 1): Decimal("0.30")})
        self.assertIsInstance(totals[1, 1], Decimal)

    def test_cap_and_rounding_apply_to_optimised_groups(self):
        orders = [order(1, Decimal("0.09"), baseline=Decimal("0.10"), logistics=0, retailer_id=1),
                  order(2, Decimal("0.09"), baseline=Decimal("0.10"), logistics=0, retailer_id=1),
                  order(3, Decimal("0.01"), baseline=0, logistics=0, retailer_id=2)]
        rows, totals, _ = evaluate_optimised_plan(
            orders, [supplier(1, Decimal("0.19"), Decimal("0.01"))],
            price_tiers(1, [(Decimal("0.19"), 0)]), [], as_of=TODAY,
        )

        result, = rows
        first, second = result["proposed_retailer_costs"]
        self.assertEqual((first["baseline_cap"], first["proposed_cost"]), ("0.01", "0.01"))
        self.assertEqual([order["proposed_cost"] for order in first["orders"]], ["0.01", "0.00"])
        self.assertEqual((second["baseline_cap"], second["proposed_cost"]), ("0.00", "0.00"))
        self.assertEqual(totals, {(1, 1): Decimal("0.19")})
        self.assert_coverage(rows, [1, 2, 3])

    def test_quote_below_raw_baseline_cannot_exceed_cent_caps(self):
        orders = [order(i, Decimal("0.09"), baseline=Decimal("0.10"), logistics=10) for i in (1, 2)]
        rows, totals, _ = evaluate_optimised_plan(
            orders, [supplier(1, Decimal("0.18"), Decimal("20.01"))],
            price_tiers(1, [(Decimal("0.01"), 0)]), [], as_of=TODAY,
        )

        self.assertTrue(all(row["procurement"] == "baseline" for row in rows))
        self.assertTrue(all(row["proposed_retailer_costs"] == [] for row in rows))
        self.assertEqual(totals, {})
        self.assert_coverage(rows, [1, 2])

    def test_equal_cost_partitions_are_deterministic_under_reordering(self):
        orders = [order(i, 100) for i in range(1, 5)]
        offers = [supplier(i, 200, 500) for i in (1, 2)]
        prices = price_tiers(1, [(1, 100), (200, 80)]) + price_tiers(2, [(1, 100), (200, 80)])

        first = evaluate_optimised_plan(orders, offers, prices, [], as_of=TODAY)
        reversed_inputs = evaluate_optimised_plan(orders[::-1], offers[::-1], prices[::-1], [], as_of=TODAY)

        self.assertEqual(first, reversed_inputs)
        self.assertEqual([(row["retailer_ids"], row["proposed_offer_id"]) for row in first[0]],
                         [([1, 2], 1), ([3, 4], 2)])

    def test_invalid_order_identity_is_rejected_before_planning(self):
        duplicate = [order(1), order(1, window=2)]
        missing_id = order(2)
        del missing_id["id"]
        for orders, message in ((duplicate, "Duplicate committed order IDs"), ([missing_id], "order ID")):
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                evaluate_optimised_plan(orders, [offer(1)], tiers(), [], as_of=TODAY)

    def test_each_limit_returns_a_complete_recomputed_fixed_batch_plan(self):
        inputs = subset_scenario()
        expected_rows, expected_totals = evaluate_plan(*inputs, as_of=TODAY)
        for limits, reason in (
            (GroupPlanningLimits(max_retailers_per_bucket=2), "retailer bundle limit"),
            (GroupPlanningLimits(max_quote_evaluations=6), "group-offer evaluation limit"),
            (GroupPlanningLimits(max_search_nodes=3), "search node limit"),
        ):
            with self.subTest(reason=reason):
                rows, totals, planning = evaluate_optimised_plan(*inputs, as_of=TODAY, limits=limits)

                self.assertEqual(planning["planning_status"], "fallback")
                self.assertIn(reason, planning["fallback_reason"])
                self.assertEqual([{key: row[key] for key in expected_rows[0]} for row in rows], expected_rows)
                self.assertEqual(totals, expected_totals)
                self.assert_coverage(rows, [1, 2, 3, 4])

    def test_group_offer_evaluation_limit_applies_across_buckets(self):
        orders = [order(1, 100), order(2, 100, window=2)]
        for maximum, expected in ((1, "fallback"), (2, "exact")):
            with self.subTest(maximum=maximum):
                _, _, planning = evaluate_optimised_plan(
                    orders, [offer(1)], tiers(), [], as_of=TODAY,
                    limits=GroupPlanningLimits(max_quote_evaluations=maximum),
                )
                self.assertEqual(planning["planning_status"], expected)

    def test_fixed_batch_fallback_keeps_baseline_at_its_own_limit(self):
        orders = [order(i, 400, window=i) for i in range(1, 18)]

        rows, totals, planning = evaluate_optimised_plan(
            orders, [offer(1)], tiers(), [], as_of=TODAY, limits=GroupPlanningLimits(max_search_nodes=1),
        )

        self.assertEqual(planning["planning_status"], "fallback")
        self.assertIn("fixed-batch planner also reached its limit", planning["fallback_reason"])
        self.assertTrue(all(row["decision"] == "REJECT_PLANNING_LIMIT" for row in rows))
        self.assertTrue(all(row["procurement"] == "baseline" for row in rows))
        self.assertEqual(totals, {})
        self.assert_coverage(rows, range(1, 18))

    def test_exact_solver_matches_exhaustive_small_assignments(self):
        random = Random(267)
        capacity = {1: Decimal(3), 2: Decimal(2)}
        for _ in range(20):
            pairs = random.sample([(mask, offer_id) for mask in range(1, 16) for offer_id in capacity], 8)
            candidates = [GroupOffer(mask, offer_id, Decimal(mask.bit_count()), Decimal(random.randrange(1, 20)))
                          for mask, offer_id in pairs]
            best = Decimal(0)
            for size in range(1, len(candidates) + 1):
                for selection in combinations(candidates, size):
                    covered = 0
                    used = dict.fromkeys(capacity, Decimal(0))
                    for option in selection:
                        if covered & option.members:
                            break
                        covered |= option.members
                        used[option.offer_id] += option.quantity_kg
                    else:
                        if all(used[offer_id] <= capacity[offer_id] for offer_id in capacity):
                            best = max(best, sum(option.savings for option in selection))

            selected = plan_groups(candidates, capacity, 100_000)
            self.assertEqual(sum(option.savings for option in selected), best)


if __name__ == "__main__":
    unittest.main()
