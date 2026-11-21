
"""Regression tests for ButcherBridge procurement decisions."""

import unittest
from datetime import date

from decision_engine import evaluate


TODAY = date(2026, 11, 19)


def order(
    i,
    q=100,
    baseline=95,
    logistics=600,
    area="Soweto",
    status="committed",
    window=1,
    retailer_id=None,
    needed_date="2026-12-08",
):
    """Create a simulated retailer order for testing."""

    if retailer_id is None:
        retailer_id = i

    return {
        "id": i,
        "retailer_id": retailer_id,
        "retailer_name": f"R{retailer_id}",
        "window_id": window,
        "product_id": 1,
        "needed_date": needed_date,
        "delivery_area": area,
        "quantity_kg": q,
        "baseline_price_per_kg": baseline,
        "baseline_logistics_cost": logistics,
        "baseline_trips": 1,
        "baseline_distance_km": 20,
        "status": status,
        "evidence_type": "simulated",
    }


def offer(
    i,
    capacity=650,
    price=82,
    area="Soweto",
    fixed=600,
):
    """Create a simulated supplier offer."""

    return {
        "id": i,
        "product_id": 1,
        "supplier_name": f"S{i}",
        "capacity_kg": capacity,
        "lead_days": 3,
        "fill_rate": 0.98,
        "service_area": area,
        "fixed_delivery": fixed,
        "variable_delivery_per_kg": 1,
        "handling_cost": 150,
        "coordinated_trips": 1,
        "coordinated_distance_km": 30,
        "active": True,
    }


def tiers(offer_id=1, price=82):
    """Create a single qualifying supplier price tier."""

    return [
        {
            "offer_id": offer_id,
            "min_quantity_kg": 1,
            "price_per_kg": price,
        }
    ]


class TestDecisions(unittest.TestCase):

    def test_group_saves(self):
        """Three retailers aggregate and reduce delivered cost."""

        result = evaluate(
            [
                order(1, 100),
                order(2, 150),
                order(3, 250),
            ],
            [offer(1)],
            tiers(),
            as_of=TODAY,
        )[0]

        self.assertEqual(result["decision"], "ACCEPT")
        self.assertEqual(result["quantity_kg"], 500)
        self.assertEqual(result["retailer_count"], 3)

        self.assertAlmostEqual(
            result["baseline_total"], 49300
        )

        self.assertAlmostEqual(
            result["best"]["total_cost"], 42250
        )

        self.assertAlmostEqual(
            result["savings_pct"], 14.30
        )

        self.assertAlmostEqual(
            result["recommended_savings_pct"], 14.30
        )

        self.assertAlmostEqual(
            sum(
                a["allocated_cost"]
                for a in result["allocated_costs"]
            ),
            42250,
        )

    def test_individual_keep_baseline(self):
        """One retailer retains its cheaper existing arrangement."""

        result = evaluate(
            [order(1, 100, baseline=70)],
            [offer(1)],
            tiers(),
            as_of=TODAY,
        )[0]

        self.assertEqual(
            result["decision"],
            "INDIVIDUAL_KEEP_BASELINE",
        )

        self.assertEqual(result["retailer_count"], 1)

        self.assertLess(
            result["baseline_total"],
            result["best"]["total_cost"],
        )

        self.assertEqual(
            result["recommended_savings_pct"], 0
        )

    def test_individual_better_quote(self):
        """One retailer receives a cheaper feasible quotation."""

        result = evaluate(
            [order(1, 100, baseline=110)],
            [offer(1)],
            tiers(),
            as_of=TODAY,
        )[0]

        self.assertEqual(
            result["decision"],
            "INDIVIDUAL_BETTER_QUOTE",
        )

        self.assertGreater(
            result["recommended_savings_pct"], 0
        )

        self.assertEqual(result["retailer_count"], 1)

    def test_multiple_orders_same_retailer(self):
        """Two orders from one retailer are not aggregation."""

        result = evaluate(
            [
                order(1, 100, retailer_id=10),
                order(2, 150, retailer_id=10),
            ],
            [offer(1)],
            tiers(),
            as_of=TODAY,
        )[0]

        self.assertEqual(result["orders"], 2)
        self.assertEqual(result["retailer_count"], 1)

        self.assertEqual(
            result["decision"],
            "INDIVIDUAL_BETTER_QUOTE",
        )

    def test_no_savings_rejected(self):
        """Multi-retailer aggregation is rejected when more costly."""

        result = evaluate(
            [
                order(1, 100, baseline=70),
                order(2, 150, baseline=70),
            ],
            [offer(1)],
            tiers(),
            as_of=TODAY,
        )[0]

        self.assertEqual(
            result["decision"],
            "REJECT_NOT_CHEAPER",
        )

        self.assertLess(result["savings_pct"], 0)

        self.assertEqual(
            result["recommended_savings_pct"], 0
        )

    def test_equal_cost_rejected(self):
        """Equal-cost aggregation is not a genuine saving."""

        # Two orders of 100 kg each.
        # Supplier total = 200*82 + 600 + 200 + 150
        #                = R17,350
        # Baseline = 200*83.75 + 2*300
        #          = R17,350

        result = evaluate(
            [
                order(
                    1, 100,
                    baseline=83.75,
                    logistics=300,
                ),
                order(
                    2, 100,
                    baseline=83.75,
                    logistics=300,
                ),
            ],
            [offer(1)],
            tiers(),
            as_of=TODAY,
        )[0]

        self.assertEqual(
            result["baseline_total"], 17350
        )

        self.assertEqual(
            result["best"]["total_cost"], 17350
        )

        self.assertEqual(
            result["decision"],
            "REJECT_NOT_CHEAPER",
        )

        self.assertEqual(
            result["recommended_savings_pct"], 0
        )

    def test_capacity_conflict_rejected(self):
        """Supplier must have enough unreserved capacity."""

        result = evaluate(
            [order(1, 500)],
            [offer(1, capacity=650)],
            tiers(),
            reserved={(1, 2): 200},
            as_of=TODAY,
        )[0]

        self.assertEqual(
            result["decision"],
            "REJECT_NO_FEASIBLE_SUPPLIER",
        )

        self.assertEqual(
            result["offers"][0]["available_kg"], 450
        )

        self.assertIn(
            "Insufficient",
            result["offers"][0]["reasons"][0],
        )

    def test_incompatible_and_withdrawn_excluded(self):
        """Different areas stay separate; withdrawn demand is excluded."""

        results = evaluate(
            [
                order(1),
                order(2, area="Pretoria"),
                order(3, status="withdrawn"),
            ],
            [offer(1)],
            tiers(),
            as_of=TODAY,
        )

        self.assertEqual(len(results), 2)

        self.assertEqual(
            sum(r["quantity_kg"] for r in results),
            200,
        )

    def test_different_dates_not_aggregated(self):
        """Orders requiring delivery on different dates stay separate."""

        results = evaluate(
            [
                order(1, needed_date="2026-12-08"),
                order(2, needed_date="2026-12-10"),
            ],
            [offer(1)],
            tiers(),
            as_of=TODAY,
        )

        self.assertEqual(len(results), 2)

        self.assertTrue(
            all(r["retailer_count"] == 1 for r in results)
        )

    def test_no_service_area(self):
        """Supplier outside the delivery area is not eligible."""

        result = evaluate(
            [order(1)],
            [offer(1, area="Pretoria")],
            tiers(),
            as_of=TODAY,
        )[0]

        self.assertEqual(
            result["decision"],
            "REJECT_NO_FEASIBLE_SUPPLIER",
        )

        self.assertIn(
            "Outside service area",
            result["offers"][0]["reasons"],
        )

    def test_separate_vs_coordinated_measures(self):
        """Baseline trips and proposed trips are recorded separately."""

        result = evaluate(
            [order(1), order(2)],
            [offer(1)],
            tiers(),
            as_of=TODAY,
        )[0]

        self.assertEqual(result["baseline_trips"], 2)

        self.assertEqual(
            result["best"]["delivery_trips"], 1
        )

        self.assertEqual(
            result["baseline_distance_km"], 40
        )

        self.assertEqual(
            result["best"]["distance_km"], 30
        )

    def test_tier_highest_threshold(self):
        """The highest qualifying quantity-price tier is selected."""

        price_tiers = [
            {
                "offer_id": 1,
                "min_quantity_kg": 1,
                "price_per_kg": 95,
            },
            {
                "offer_id": 1,
                "min_quantity_kg": 150,
                "price_per_kg": 82,
            },
        ]

        result = evaluate(
            [order(1), order(2)],
            [offer(1)],
            price_tiers,
            as_of=TODAY,
        )[0]

        self.assertEqual(
            result["best"]["tier_min_kg"], 150
        )

        self.assertEqual(
            result["best"]["cost_per_kg"], 86.75
        )


if __name__ == "__main__":
    unittest.main()
