
"""Regression tests for ButcherBridge procurement and input validation."""

import unittest
from datetime import date
from decision_engine import evaluate

TODAY = date(2026, 11, 19)


def order(i, q=100, baseline=95, logistics=600, area="Soweto",
          status="committed", window=1, retailer_id=None,
          needed_date="2026-12-08"):
    """Make a simulated order; default retailer ID matches order ID."""
    retailer_id = i if retailer_id is None else retailer_id
    return {
        "id": i, "retailer_id": retailer_id,
        "retailer_name": f"R{retailer_id}", "window_id": window,
        "product_id": 1, "needed_date": needed_date, "delivery_area": area,
        "quantity_kg": q, "baseline_price_per_kg": baseline,
        "baseline_logistics_cost": logistics, "baseline_trips": 1,
        "baseline_distance_km": 20, "status": status,
        "evidence_type": "simulated",
    }


def offer(i, capacity=650, price=82, area="Soweto", fixed=600):
    """Make a simulated supplier offer."""
    return {
        "id": i, "product_id": 1, "supplier_name": f"S{i}",
        "capacity_kg": capacity, "lead_days": 3, "fill_rate": 0.98,
        "service_area": area, "fixed_delivery": fixed,
        "variable_delivery_per_kg": 1, "handling_cost": 150,
        "coordinated_trips": 1, "coordinated_distance_km": 30,
        "active": True,
    }


def tiers(offer_id=1, price=82):
    return [{"offer_id": offer_id, "min_quantity_kg": 1,
             "price_per_kg": price}]


class TestDecisions(unittest.TestCase):
    """Existing 17 regressions and six supplier validation regressions."""

    def evaluate_one(self, orders=None, offers=None, price_tiers=None, **kwargs):
        """Run a scenario and return its first compatible batch."""
        return evaluate(
            [order(1)] if orders is None else orders,
            [offer(1)] if offers is None else offers,
            tiers() if price_tiers is None else price_tiers,
            as_of=TODAY, **kwargs,
        )[0]

    # Existing procurement and compatibility tests

    def test_group_saves(self):
        r = self.evaluate_one(orders=[order(1, 100), order(2, 150), order(3, 250)])
        self.assertEqual(r["decision"], "ACCEPT")
        self.assertEqual(r["quantity_kg"], 500)
        self.assertEqual(r["retailer_count"], 3)
        self.assertAlmostEqual(r["baseline_total"], 49300)
        self.assertAlmostEqual(r["best"]["total_cost"], 42250)
        self.assertAlmostEqual(r["savings_pct"], 14.30)
        self.assertAlmostEqual(r["recommended_savings_pct"], 14.30)
        self.assertAlmostEqual(sum(a["allocated_cost"] for a in r["allocated_costs"]), 42250)

    def test_individual_keep_baseline(self):
        r = self.evaluate_one(orders=[order(1, 100, baseline=70)])
        self.assertEqual(r["decision"], "INDIVIDUAL_KEEP_BASELINE")
        self.assertEqual(r["retailer_count"], 1)
        self.assertLess(r["baseline_total"], r["best"]["total_cost"])
        self.assertEqual(r["recommended_savings_pct"], 0)

    def test_individual_better_quote(self):
        r = self.evaluate_one(orders=[order(1, 100, baseline=110)])
        self.assertEqual(r["decision"], "INDIVIDUAL_BETTER_QUOTE")
        self.assertGreater(r["recommended_savings_pct"], 0)
        self.assertEqual(r["retailer_count"], 1)

    def test_multiple_orders_same_retailer(self):
        r = self.evaluate_one(orders=[order(1, retailer_id=10),
                                       order(2, 150, retailer_id=10)])
        self.assertEqual(r["orders"], 2)
        self.assertEqual(r["retailer_count"], 1)
        self.assertEqual(r["decision"], "INDIVIDUAL_BETTER_QUOTE")

    def test_no_savings_rejected(self):
        r = self.evaluate_one(orders=[order(1, baseline=70),
                                       order(2, 150, baseline=70)])
        self.assertEqual(r["decision"], "REJECT_NOT_CHEAPER")
        self.assertLess(r["savings_pct"], 0)
        self.assertEqual(r["recommended_savings_pct"], 0)

    def test_equal_cost_rejected(self):
        # 200*82 + 600 + 200 + 150 = 200*83.75 + 2*300 = R17,350
        r = self.evaluate_one(orders=[order(1, baseline=83.75, logistics=300),
                                       order(2, baseline=83.75, logistics=300)])
        self.assertEqual(r["baseline_total"], 17350)
        self.assertEqual(r["best"]["total_cost"], 17350)
        self.assertEqual(r["decision"], "REJECT_NOT_CHEAPER")
        self.assertEqual(r["recommended_savings_pct"], 0)

    def test_capacity_conflict_rejected(self):
        r = self.evaluate_one(orders=[order(1, 500)],
                              offers=[offer(1, capacity=650)],
                              reserved={(1, 2): 200})
        self.assertEqual(r["decision"], "REJECT_NO_FEASIBLE_SUPPLIER")
        self.assertEqual(r["offers"][0]["available_kg"], 450)
        self.assertIn("Insufficient", r["offers"][0]["reasons"][0])

    def test_incompatible_and_withdrawn_excluded(self):
        results = evaluate([order(1), order(2, area="Pretoria"),
                            order(3, status="withdrawn")], [offer(1)],
                           tiers(), as_of=TODAY)
        self.assertEqual(len(results), 2)
        self.assertEqual(sum(r["quantity_kg"] for r in results), 200)

    def test_different_dates_not_aggregated(self):
        results = evaluate([order(1, needed_date="2026-12-08"),
                            order(2, needed_date="2026-12-10")],
                           [offer(1)], tiers(), as_of=TODAY)
        self.assertEqual(len(results), 2)
        self.assertTrue(all(r["retailer_count"] == 1 for r in results))

    def test_no_service_area(self):
        r = self.evaluate_one(offers=[offer(1, area="Pretoria")])
        self.assertEqual(r["decision"], "REJECT_NO_FEASIBLE_SUPPLIER")
        self.assertIn("Outside service area", r["offers"][0]["reasons"])

    def test_separate_vs_coordinated_measures(self):
        r = self.evaluate_one(orders=[order(1), order(2)])
        self.assertEqual(r["baseline_trips"], 2)
        self.assertEqual(r["best"]["delivery_trips"], 1)
        self.assertEqual(r["baseline_distance_km"], 40)
        self.assertEqual(r["best"]["distance_km"], 30)

    def test_tier_highest_threshold(self):
        price_tiers = [
            {"offer_id": 1, "min_quantity_kg": 1, "price_per_kg": 95},
            {"offer_id": 1, "min_quantity_kg": 150, "price_per_kg": 82},
        ]
        r = self.evaluate_one(orders=[order(1), order(2)],
                              price_tiers=price_tiers)
        self.assertEqual(r["best"]["tier_min_kg"], 150)
        self.assertEqual(r["best"]["cost_per_kg"], 86.75)

    # Previously added retailer-input tests

    def test_zero_quantity_rejected(self):
        with self.assertRaisesRegex(ValueError, "quantity_kg must be positive"):
            self.evaluate_one(orders=[order(1, q=0)])

    def test_negative_quantity_rejected(self):
        with self.assertRaisesRegex(ValueError, "quantity_kg must be positive"):
            self.evaluate_one(orders=[order(1, q=-100)])

    def test_negative_baseline_cost_rejected(self):
        with self.assertRaisesRegex(ValueError, "baseline_price_per_kg cannot be negative"):
            self.evaluate_one(orders=[order(1, baseline=-50)])

    def test_missing_retailer_rejected(self):
        invalid_order = order(1)
        del invalid_order["retailer_id"]
        with self.assertRaisesRegex(ValueError, "retailer_id is required"):
            self.evaluate_one(orders=[invalid_order])

    def test_nonfinite_quantity_rejected(self):
        with self.assertRaisesRegex(ValueError, "quantity_kg must be finite"):
            self.evaluate_one(orders=[order(1, q=float("nan"))])

    # New supplier-input tests

    def test_negative_supplier_delivery_cost_rejected(self):
        invalid_offer = offer(1)
        invalid_offer["fixed_delivery"] = -500
        with self.assertRaisesRegex(ValueError, "fixed_delivery cannot be negative"):
            self.evaluate_one(offers=[invalid_offer])

    def test_supplier_fill_rate_above_one_rejected(self):
        invalid_offer = offer(1)
        invalid_offer["fill_rate"] = 1.2
        with self.assertRaisesRegex(ValueError, "fill_rate cannot exceed 1"):
            self.evaluate_one(offers=[invalid_offer])

    def test_negative_supplier_capacity_rejected(self):
        with self.assertRaisesRegex(ValueError, "capacity_kg must be positive"):
            self.evaluate_one(offers=[offer(1, capacity=-100)])

    def test_negative_price_tier_rejected(self):
        with self.assertRaisesRegex(ValueError, "price_per_kg cannot be negative"):
            self.evaluate_one(price_tiers=tiers(price=-20))

    def test_negative_reservation_rejected(self):
        with self.assertRaisesRegex(ValueError, "quantity_kg cannot be negative"):
            self.evaluate_one(reserved={(1, 2): -100})

    def test_fractional_supplier_lead_time_rejected(self):
        invalid_offer = offer(1)
        invalid_offer["lead_days"] = 2.5
        with self.assertRaisesRegex(ValueError, "lead_days must be a whole number"):
            self.evaluate_one(offers=[invalid_offer])


class TestJointCapacity(unittest.TestCase):
    def test_two_400_kg_batches_share_one_650_kg_offer(self):
        orders = [order(1, 200), order(2, 200),
                  order(3, 200, window=2), order(4, 200, window=2)]
        first, second = evaluate(orders, [offer(1)], tiers(), as_of=TODAY)

        self.assertEqual(first["decision"], "ACCEPT")
        self.assertEqual(second["decision"], "REJECT_NO_FEASIBLE_SUPPLIER")
        self.assertEqual(first["proposed_offer_id"], 1)
        self.assertIsNone(second["proposed_offer_id"])
        self.assertIsNone(second["best"])
        self.assertTrue(second["offers"][0]["eligible"])
        self.assertIn("shared capacity", second["reason"])
        self.assertEqual(second["recommended_savings_pct"], 0)
        self.assertEqual(second["allocated_costs"], [])
        self.assertEqual(first["best"]["total_cost"] + second["baseline_total"], 73150)

    def test_two_suppliers_move_the_flexible_batch_to_the_second_quote(self):
        orders = [order(1, 200), order(2, 200),
                  order(3, 200, window=2, needed_date="2026-11-24"),
                  order(4, 200, window=2, needed_date="2026-11-24")]
        slower = offer(2, capacity=400)
        slower["lead_days"] = 10

        flexible, urgent = evaluate(
            orders, [offer(1), slower], tiers() + tiers(2, price=87), as_of=TODAY,
        )

        self.assertEqual([flexible["decision"], urgent["decision"]], ["ACCEPT", "ACCEPT"])
        self.assertEqual(flexible["proposed_offer_id"], 2)
        self.assertEqual(urgent["proposed_offer_id"], 1)
        self.assertEqual(flexible["best"]["offer_id"], 2)
        self.assertEqual(urgent["best"]["offer_id"], 1)
        self.assertEqual(flexible["best"]["total_cost"] + urgent["best"]["total_cost"], 69900)

    def test_reservations_in_all_windows_reduce_available_capacity(self):
        orders = [order(1, 200), order(2, 200),
                  order(3, 200, window=2), order(4, 200, window=2)]
        reserved = {(1, 1): 150, (1, 3): 50}
        results = evaluate(orders, [offer(1, capacity=950)], tiers(),
                           reserved=reserved, as_of=TODAY)

        self.assertEqual([r["offers"][0]["available_kg"] for r in results], [750, 750])
        self.assertEqual([r["proposed_offer_id"] for r in results], [1, None])
        self.assertEqual(reserved, {(1, 1): 150, (1, 3): 50})

    def test_two_smaller_batches_can_save_more_than_one_larger_batch(self):
        orders = [order(1, 200), order(2, 200),
                  order(3, 150, window=2), order(4, 150, window=2),
                  order(5, 150, window=3), order(6, 150, window=3)]
        large, small_a, small_b = evaluate(orders, [offer(1)], tiers(), as_of=TODAY)

        self.assertEqual([r["proposed_offer_id"] for r in (large, small_a, small_b)],
                         [None, 1, 1])
        self.assertEqual(large["baseline_total"] + small_a["best"]["total_cost"]
                         + small_b["best"]["total_cost"], 90500)

    def test_individual_better_quote_uses_the_same_shared_capacity(self):
        orders = [order(1, 200), order(2, 200), order(3, 400, baseline=110, window=2)]
        group, individual = evaluate(orders, [offer(1)], tiers(), as_of=TODAY)

        self.assertIsNone(group["proposed_offer_id"])
        self.assertEqual(individual["decision"], "INDIVIDUAL_BETTER_QUOTE")
        self.assertEqual(individual["proposed_offer_id"], 1)

    def test_tied_plan_and_cost_shares_are_input_order_independent(self):
        orders = [order(1, 100.05), order(2, 299.95),
                  order(3, 125, window=2), order(4, 275, window=2)]
        offers = [offer(2), offer(1)]
        price_tiers = tiers(2) + tiers()

        results = evaluate(orders, offers, price_tiers, as_of=TODAY)
        reversed_results = evaluate(orders[::-1], offers[::-1], price_tiers[::-1], as_of=TODAY)

        self.assertEqual(results, reversed_results)
        self.assertEqual([r["proposed_offer_id"] for r in results], [1, 2])

    def test_oversized_conflict_uses_baseline_with_an_explicit_reason(self):
        # Seventeen batches with one cheaper offer each have 2**17 combinations.
        orders = [order(i, 400, window=i) for i in range(1, 18)]
        results = evaluate(orders, [offer(1)], tiers(), as_of=TODAY)

        self.assertEqual(len(results), 17)
        for batch in results:
            self.assertEqual(batch["decision"], "REJECT_PLANNING_LIMIT")
            self.assertIn("planning limit", batch["reason"])
            self.assertIsNone(batch["proposed_offer_id"])
            self.assertEqual(batch["recommended_savings_pct"], 0)

    def test_large_feasible_set_can_use_the_cheapest_offer_for_each_batch(self):
        orders = [order(i, 400, window=i) for i in range(1, 18)]
        results = evaluate(orders, [offer(1, capacity=6800)], tiers(), as_of=TODAY)

        self.assertEqual([r["proposed_offer_id"] for r in results], [1] * 17)


if __name__ == "__main__":
    unittest.main()
