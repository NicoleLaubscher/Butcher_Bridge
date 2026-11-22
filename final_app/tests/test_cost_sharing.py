"""Regression tests for whole-cent, baseline-capped retailer cost sharing."""

import unittest
from decimal import Decimal

from decision_engine import evaluate, evaluate_plan
from test_decision_engine import TODAY, offer, order, tiers


def flat_offer(offer_id, fixed_cost, capacity=650):
    supplier = offer(offer_id, capacity=capacity, fixed=Decimal(fixed_cost))
    supplier.update(variable_delivery_per_kg=0, handling_cost=0)
    return supplier


def price_tier(offer_id, price="0"):
    return {
        "offer_id": offer_id,
        "min_quantity_kg": Decimal("0.01"),
        "price_per_kg": Decimal(price),
    }


def borderline_orders():
    return [order(i, Decimal("0.09"), baseline=Decimal("0.10"), logistics=10)
            for i in (1, 2)]


class TestCostSharing(unittest.TestCase):
    def test_retailer_with_low_baseline_saves_even_with_multiple_orders(self):
        orders = [order(1, 40, baseline=70, logistics=0, retailer_id=10),
                  order(2, 60, baseline=70, logistics=0, retailer_id=10),
                  order(3, 100, baseline=120, logistics=0, retailer_id=20)]

        batch, = evaluate(orders, [offer(1)], tiers(), as_of=TODAY)

        self.assertEqual(batch["decision"], "ACCEPT")
        self.assertEqual(batch["retailer_count"], 2)
        self.assertEqual(batch["best"]["total_cost"], 17350)
        self.assertEqual(batch["baseline_total"], 19000)
        self.assertEqual(batch["proposed_retailer_costs"], [
            {"retailer_id": 10, "retailer": "R10", "baseline_cap": "7000.00",
             "proposed_cost": "6392.11", "orders": [
                 {"order_id": 1, "proposed_cost": "2556.84"},
                 {"order_id": 2, "proposed_cost": "3835.27"},
             ]},
            {"retailer_id": 20, "retailer": "R20", "baseline_cap": "12000.00",
             "proposed_cost": "10957.89", "orders": [
                 {"order_id": 3, "proposed_cost": "10957.89"},
             ]},
        ])
        self.assertEqual(batch["allocated_costs"], [
            {"order_id": 3, "retailer": "R20", "allocated_cost": 10957.89},
            {"order_id": 2, "retailer": "R10", "allocated_cost": 3835.27},
            {"order_id": 1, "retailer": "R10", "allocated_cost": 2556.84},
        ])

    def test_cap_is_floored_once_per_retailer_and_zero_baseline_gets_no_charge(self):
        orders = [order(1, Decimal("0.09"), baseline=Decimal("0.10"), logistics=0, retailer_id=10),
                  order(2, Decimal("0.09"), baseline=Decimal("0.10"), logistics=0, retailer_id=10),
                  order(3, Decimal("0.01"), baseline=0, logistics=0, retailer_id=20)]

        batch, = evaluate(orders, [flat_offer(1, "0.01")], [price_tier(1)], as_of=TODAY)

        self.assertEqual(batch["decision"], "ACCEPT")
        first, second = batch["proposed_retailer_costs"]
        self.assertEqual(first["baseline_cap"], "0.01")
        self.assertEqual(first["proposed_cost"], "0.01")
        self.assertEqual(first["orders"], [
            {"order_id": 1, "proposed_cost": "0.01"},
            {"order_id": 2, "proposed_cost": "0.00"},
        ])
        self.assertEqual(second["baseline_cap"], "0.00")
        self.assertEqual(second["proposed_cost"], "0.00")

    def test_two_cent_quote_has_nonnegative_and_input_independent_shares(self):
        # IDs are deliberately reversed across levels to distinguish the tie-breaks.
        orders = [order(i, 1, baseline=1, logistics=0, retailer_id=5 - i)
                  for i in range(1, 5)]
        supplier = flat_offer(1, "0.02")

        batch, = evaluate(orders, [supplier], [price_tier(1)], as_of=TODAY)
        reversed_batch, = evaluate(orders[::-1], [supplier], [price_tier(1)], as_of=TODAY)

        self.assertEqual(batch, reversed_batch)
        self.assertEqual(batch["decision"], "ACCEPT")
        self.assertEqual([row["proposed_cost"] for row in batch["proposed_retailer_costs"]],
                         ["0.01", "0.01", "0.00", "0.00"])
        self.assertEqual([row["allocated_cost"] for row in batch["allocated_costs"]],
                         [0.01, 0.01, 0.0, 0.0])

    def test_zero_total_with_zero_caps_only_proposes_when_raw_baseline_is_positive(self):
        for baseline_price, expected_decision in ((0, "REJECT_NOT_CHEAPER"),
                                                   (Decimal("0.10"), "ACCEPT")):
            with self.subTest(baseline_price=baseline_price):
                orders = [order(i, Decimal("0.09"), baseline=baseline_price, logistics=0)
                          for i in (1, 2)]
                batch, = evaluate(orders, [flat_offer(1, "0.00")], [price_tier(1)], as_of=TODAY)

                shares = batch["proposed_retailer_costs"]
                self.assertEqual(batch["decision"], expected_decision)
                self.assertEqual([row["proposed_cost"] for row in shares],
                                 ["0.00", "0.00"] if baseline_price else [])
                self.assertEqual([row["allocated_cost"] for row in batch["allocated_costs"]], [0, 0])

    def test_exact_retailer_and_order_totals_for_quotes_above_float_cent_precision(self):
        orders = [order(i, Decimal(f"100000000.0{i}"), baseline=Decimal("120000000.01"),
                        logistics=0, retailer_id=10 if i < 3 else 20) for i in (1, 2, 3)]
        supplier = flat_offer(1, "0.05", capacity=Decimal("400000000.00"))

        batch, = evaluate(orders, [supplier], [price_tier(1, "100000000.01")], as_of=TODAY)

        self.assertEqual(batch["decision"], "ACCEPT")
        shares = batch["proposed_retailer_costs"]
        self.assertEqual(sum(Decimal(row["proposed_cost"]) for row in shares),
                         Decimal("30000000009000000.05"))
        for row in shares:
            self.assertEqual(sum(Decimal(line["proposed_cost"]) for line in row["orders"]),
                             Decimal(row["proposed_cost"]))
            self.assertLessEqual(Decimal(row["proposed_cost"]), Decimal(row["baseline_cap"]))

    def test_equal_and_higher_quotes_keep_only_diagnostic_shares(self):
        orders = [order(1, 1, baseline=10, logistics=0), order(2, 1, baseline=10, logistics=0)]
        for total in ("20.00", "20.01"):
            with self.subTest(total=total):
                batch, = evaluate(orders, [flat_offer(1, total)], [price_tier(1)], as_of=TODAY)

                self.assertEqual(batch["decision"], "REJECT_NOT_CHEAPER")
                self.assertIsNone(batch["best"]["cost_sharing_reason"])
                self.assertIsNone(batch["proposed_offer_id"])
                self.assertEqual(batch["recommended_savings_pct"], 0)
                self.assertEqual(batch["proposed_retailer_costs"], [])
                self.assertEqual(sum(Decimal(str(row["allocated_cost"]))
                                     for row in batch["allocated_costs"]), Decimal(total))

    def test_subcent_savings_do_not_admit_an_unallocatable_quote(self):
        batches, totals = evaluate_plan(
            borderline_orders(), [flat_offer(1, "20.00")], [price_tier(1, "0.05")], [], as_of=TODAY,
        )

        batch, = batches
        self.assertEqual(batch["decision"], "REJECT_NOT_CHEAPER")
        self.assertTrue(batch["best"]["eligible"])
        self.assertEqual(batch["best"]["total_cost"], 20.01)
        self.assertIn("shared in whole cents", batch["reason"])
        self.assertIn("cheaper than the combined baseline", batch["best"]["cost_sharing_reason"])
        self.assertGreater(batch["savings_pct"], 0)
        self.assertEqual(batch["recommended_savings_pct"], 0)
        self.assertEqual(batch["proposed_retailer_costs"], [])
        self.assertEqual(totals, {})

    def test_joint_plan_can_select_a_fair_alternative_supplier(self):
        offers = [flat_offer(1, "19.95", capacity=Decimal("0.18")),
                  flat_offer(2, "20.01"), flat_offer(3, "20.00")]
        offers[1]["lead_days"] = offers[2]["lead_days"] = 10
        urgent_order = order(3, Decimal("0.18"), baseline=1, logistics=20,
                             window=2, needed_date="2026-11-24")
        batches, totals = evaluate_plan(
            borderline_orders() + [urgent_order], offers, [price_tier(i) for i in (1, 2, 3)],
            [], as_of=TODAY,
        )

        batch, urgent = batches
        self.assertEqual(batch["decision"], "ACCEPT")
        self.assertIn("shared in whole cents", batch["offers"][1]["cost_sharing_reason"])
        self.assertEqual(batch["proposed_offer_id"], 3)
        self.assertEqual(urgent["proposed_offer_id"], 1)
        self.assertEqual([row["proposed_cost"] for row in batch["proposed_retailer_costs"]],
                         ["10.00", "10.00"])
        self.assertEqual(totals, {(3, 1): Decimal("0.18"), (1, 2): Decimal("0.18")})

    def test_excluding_an_unallocatable_quote_frees_capacity_for_another_batch(self):
        # Window 1 would save R0.008. Window 2 saves R0.0044 and can recover the entire quote.
        orders = borderline_orders() + [order(3, Decimal("0.18"), baseline=Decimal("0.08"),
                                               logistics=20, window=2)]
        supplier = flat_offer(1, "20.00", capacity=Decimal("0.18"))

        batches, totals = evaluate_plan(orders, [supplier], [price_tier(1, "0.05")], [], as_of=TODAY)

        rejected, selected = batches
        self.assertEqual(rejected["decision"], "REJECT_NOT_CHEAPER")
        self.assertIsNone(rejected["proposed_offer_id"])
        self.assertEqual(selected["decision"], "INDIVIDUAL_BETTER_QUOTE")
        self.assertEqual(selected["proposed_offer_id"], 1)
        self.assertEqual(selected["proposed_retailer_costs"][0]["proposed_cost"], "20.01")
        self.assertEqual(totals, {(1, 2): Decimal("0.18")})


if __name__ == "__main__":
    unittest.main()
