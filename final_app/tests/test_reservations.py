"""Reservation planning and read-only Flask tests with simulated data."""

import unittest
from contextlib import nullcontext
from datetime import date, timedelta
from decimal import Decimal
from secrets import token_hex
from unittest.mock import patch

from decision_engine import evaluate_plan
from test_decision_engine import TODAY, offer, order, tiers

with patch("dotenv.load_dotenv"):
    import app as bridge_app


def allocation(offer_id, window_id, quantity, status):
    return {
        "offer_id": offer_id,
        "window_id": window_id,
        "quantity_kg": Decimal(quantity),
        "status": status,
    }


class TestReservationPlanning(unittest.TestCase):
    def test_reserved_key_blocks_a_quote_and_consumes_capacity_in_other_windows(self):
        batches, totals = evaluate_plan(
            [order(1, 100), order(2, 500, window=2)], [offer(1)], tiers(),
            [allocation(1, 1, "200.00", "reserved")], as_of=TODAY,
        )

        first, second = batches
        occupied = first["offers"][0]
        free = second["offers"][0]
        self.assertTrue(occupied["eligible"])
        self.assertEqual(occupied["reservation_key_status"], "reserved")
        self.assertEqual(free["reservation_key_status"], "free")
        self.assertEqual(free["reserved_kg"], 200)
        self.assertEqual(free["available_kg"], 450)
        self.assertFalse(free["eligible"])
        self.assertEqual(first["decision"], "REJECT_NO_FEASIBLE_SUPPLIER")
        self.assertIn("allocation rows", first["reason"])
        self.assertEqual(first["recommended_savings_pct"], 0)
        self.assertIsNone(first["proposed_offer_id"])
        self.assertEqual(totals, {})

    def test_released_key_blocks_a_quote_but_consumes_no_capacity(self):
        batches, totals = evaluate_plan(
            [order(1, 100), order(2, 650, window=2)], [offer(1)], tiers(),
            [allocation(1, 1, "200.00", "released")], as_of=TODAY,
        )

        occupied = batches[0]["offers"][0]
        self.assertTrue(occupied["eligible"])
        self.assertEqual(occupied["reservation_key_status"], "released")
        self.assertEqual(occupied["reserved_kg"], 0)
        self.assertEqual(occupied["available_kg"], 650)
        self.assertIsNone(batches[0]["proposed_offer_id"])
        self.assertEqual(batches[1]["proposed_offer_id"], 1)
        self.assertEqual(totals, {(1, 2): Decimal("650")})

    def test_alternative_supplier_wins_when_the_cheapest_key_is_occupied(self):
        batches, totals = evaluate_plan(
            [order(1, 200), order(2, 200)], [offer(1), offer(2)],
            tiers() + tiers(2, price=87),
            [allocation(1, 1, "100.00", "reserved")], as_of=TODAY,
        )

        batch = batches[0]
        self.assertEqual(batch["decision"], "ACCEPT")
        self.assertTrue(batch["offers"][0]["eligible"])
        self.assertLess(batch["offers"][0]["total_cost"], batch["best"]["total_cost"])
        self.assertEqual(batch["proposed_offer_id"], 2)
        self.assertEqual(batch["best"]["total_cost"], 35950)
        self.assertEqual(batch["recommended_savings_pct"], 8.29)
        self.assertEqual(totals, {(2, 1): Decimal("400")})

    def test_withdrawn_and_fulfilled_demand_do_not_release_an_existing_hold(self):
        allocations = [allocation(1, 1, "200.00", "reserved")]
        for status in ("withdrawn", "fulfilled"):
            with self.subTest(status=status):
                batches, totals = evaluate_plan(
                    [order(1, 100, status=status), order(2, 500, window=2)],
                    [offer(1)], tiers(), allocations, as_of=TODAY,
                )

                self.assertEqual([batch["window_id"] for batch in batches], [2])
                self.assertEqual(batches[0]["offers"][0]["available_kg"], 450)
                self.assertIsNone(batches[0]["proposed_offer_id"])
                self.assertEqual(totals, {})

    def test_totals_include_only_the_batches_selected_under_shared_capacity(self):
        batches, totals = evaluate_plan(
            [order(1, 400), order(2, 400, window=2)], [offer(1, capacity=900)], tiers(),
            [allocation(1, 3, "300.00", "reserved")], as_of=TODAY,
        )

        first, second = batches
        self.assertEqual(first["proposed_offer_id"], 1)
        self.assertTrue(second["offers"][0]["eligible"])
        self.assertEqual(second["offers"][0]["reservation_key_status"], "free")
        self.assertIsNone(second["proposed_offer_id"])
        self.assertEqual(totals, {(1, 1): Decimal("400")})

    def test_batches_in_one_window_sum_exactly_and_keep_their_own_prices(self):
        supplier = offer(1, capacity=Decimal("0.30"), fixed=1)
        supplier["handling_cost"] = 0
        price_tiers = [
            {"offer_id": 1, "min_quantity_kg": Decimal("0.01"), "price_per_kg": 82},
            {"offer_id": 1, "min_quantity_kg": Decimal("0.20"), "price_per_kg": 80},
        ]
        orders = [
            order(1, Decimal("0.10"), baseline=100, logistics=0),
            order(2, Decimal("0.20"), baseline=100, logistics=0, needed_date="2026-12-09"),
        ]

        batches, totals = evaluate_plan(orders, [supplier], price_tiers, [], as_of=TODAY)

        self.assertEqual([batch["proposed_offer_id"] for batch in batches], [1, 1])
        self.assertEqual([batch["best"]["total_cost"] for batch in batches], [9.30, 17.20])
        self.assertEqual(totals, {(1, 1): Decimal("0.30")})
        self.assertIsInstance(totals[1, 1], Decimal)


class TestDecisionRoutes(unittest.TestCase):
    def setUp(self):
        regular = date.today() + timedelta(days=30)
        later = regular + timedelta(days=1)
        self.orders = [
            order(1, Decimal("200.10"), needed_date=regular),
            order(2, Decimal("200.20"), needed_date=later),
            order(3, Decimal("200.00"), baseline=70, window=2, needed_date=regular),
        ]
        self.offers = [offer(1), offer(2, capacity=Decimal("400.30"))]
        self.price_tiers = tiers() + tiers(2, price=87)
        self.allocations = [
            allocation(1, 1, "100.00", "reserved"),
            allocation(2, 2, "150.00", "released"),
        ]
        self.enterContext(patch.dict(
            bridge_app.app.config, TESTING=True, SECRET_KEY=token_hex(16),
            SESSION_COOKIE_SECURE=False,
        ))
        self.enterContext(patch("db.connection", side_effect=AssertionError("Live database access")))
        self.enterContext(patch.object(
            bridge_app, "transaction", side_effect=AssertionError("Reservation write path invoked"),
        ))
        self.query = self.enterContext(patch.object(bridge_app, "query", side_effect=self.read_rows))
        self.enterContext(patch.object(
            bridge_app, "read_snapshot", side_effect=lambda: nullcontext(self.read_rows),
        ))
        self.client = bridge_app.app.test_client()
        with self.client.session_transaction() as session:
            session["signed_in"] = True

    def read_rows(self, sql):
        self.assertTrue(sql.startswith("SELECT "))
        if sql.startswith("SELECT d.*"):
            return self.orders
        if sql.startswith("SELECT o.*"):
            return self.offers
        if "FROM price_tiers" in sql:
            return self.price_tiers
        if "FROM allocations" in sql:
            self.assertNotIn("WHERE", sql.upper())
            return self.allocations
        if "AS order_count" in sql:
            return [{"order_count": 3, "committed_kg": Decimal("600.30")}]
        if "FROM fulfilments" in sql:
            return [{"n": 0, "ordered": 0, "delivered": 0, "on_time": 0, "otif": 0}]
        self.fail("Unexpected query on a decision route")

    def test_get_decisions_returns_exact_reservation_totals_using_only_reads(self):
        response = self.client.get("/api/decisions")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        first, second, baseline = payload["items"]
        self.assertEqual([first["proposed_offer_id"], second["proposed_offer_id"]], [2, 2])
        self.assertEqual(first["decision"], "INDIVIDUAL_BETTER_QUOTE")
        self.assertEqual(first["quantity_kg"], 200.10)
        self.assertAlmostEqual(first["best"]["total_cost"], 18358.80)
        self.assertAlmostEqual(second["best"]["total_cost"], 18367.60)
        self.assertTrue(first["offers"][0]["eligible"])
        self.assertEqual(first["offers"][0]["reservation_key_status"], "reserved")
        self.assertEqual(first["offers"][0]["reserved_kg"], 100)
        self.assertEqual(first["offers"][0]["available_kg"], 550)
        self.assertEqual(first["best"]["reservation_key_status"], "free")
        self.assertEqual(first["best"]["available_kg"], 400.30)
        self.assertEqual(baseline["offers"][1]["reservation_key_status"], "released")
        self.assertEqual(baseline["decision"], "INDIVIDUAL_KEEP_BASELINE")
        self.assertEqual(baseline["recommended_savings_pct"], 0)
        self.assertEqual(payload["proposed_reservation_totals"], [
            {"offer_id": 2, "window_id": 1, "quantity_kg": "400.30"},
        ])
        allocation_reads = [call for call in self.query.call_args_list
                            if "FROM allocations" in call.args[0]]
        self.assertEqual(len(allocation_reads), 1)

    def test_dashboard_shows_capacity_quote_eligibility_proposals_and_key_status(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("Reserved kg across windows", html)
        self.assertIn("Eligible for this batch", html)
        self.assertIn("Occupied (reserved)", html)
        self.assertIn("Occupied (released)", html)
        self.assertIn("New reservation key", html)
        self.assertEqual(html.count("Proposed purchase</span>"), 2)
        self.assertIn("Single-retailer supplier purchase", html)
        self.assertIn("Potential savings vs baseline</span><strong>0.0%", html)
        self.assertIn("Potential savings vs baseline</span><strong>6.38%", html)
        self.assertIn("Actual fill rate", html)

    def test_decision_api_and_dashboard_separate_proposal_costs_from_diagnostics(self):
        regular = self.orders[0]["needed_date"]
        self.allocations = []
        self.orders = [
            order(1, Decimal("40.00"), baseline=70, logistics=0, retailer_id=10, needed_date=regular),
            order(2, Decimal("60.00"), baseline=70, logistics=0, retailer_id=10, needed_date=regular),
            order(3, Decimal("100.00"), baseline=120, logistics=0, retailer_id=20, needed_date=regular),
            order(4, 100, baseline=70, logistics=0, retailer_id=30, window=2, needed_date=regular),
            order(5, 100, baseline=70, logistics=0, retailer_id=40, window=2, needed_date=regular),
            order(6, 100, baseline=70, logistics=0, retailer_id=50, window=3, needed_date=regular),
        ]

        response = self.client.get("/api/decisions")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        proposal, rejected, individual_baseline = payload["items"]
        self.assertEqual(proposal["decision"], "ACCEPT")
        self.assertEqual(proposal["best"]["total_cost"], 17350.0)
        self.assertAlmostEqual(proposal["recommended_savings_pct"], 8.68)
        self.assertEqual([row["proposed_cost"] for row in proposal["proposed_retailer_costs"]],
                         ["6392.11", "10957.89"])
        self.assertEqual(proposal["proposed_retailer_costs"][0]["orders"], [
            {"order_id": 1, "proposed_cost": "2556.84"},
            {"order_id": 2, "proposed_cost": "3835.27"},
        ])
        self.assertEqual(rejected["decision"], "REJECT_NOT_CHEAPER")
        self.assertEqual(individual_baseline["decision"], "INDIVIDUAL_KEEP_BASELINE")
        for batch in (rejected, individual_baseline):
            self.assertEqual(batch["proposed_retailer_costs"], [])
            self.assertTrue(batch["allocated_costs"])
        for batch in payload["items"]:
            for row in batch["allocated_costs"]:
                self.assertEqual(set(row), {"order_id", "retailer", "allocated_cost"})
                self.assertIsInstance(row["allocated_cost"], float)
        self.assertEqual(payload["proposed_reservation_totals"], [
            {"offer_id": 1, "window_id": 1, "quantity_kg": "200.00"},
        ])

        dashboard = self.client.get("/")
        self.assertEqual(dashboard.status_code, 200)
        html = dashboard.get_data(as_text=True)
        self.assertEqual(html.count("<caption>Proposed retailer costs</caption>"), 1)
        self.assertEqual(html.count('<th scope="row">R10</th>'), 1)
        self.assertIn("R6392.11", html)
        self.assertIn("R10957.89", html)
        proposed_table = html.split("<caption>Proposed retailer costs</caption>", 1)[1].split("</table>", 1)[0]
        for retailer in ("R30", "R40", "R50"):
            self.assertIn(f"<strong>{retailer}</strong>", html)
            self.assertNotIn(f">{retailer}<", proposed_table)

    def test_get_decisions_returns_empty_totals_without_committed_demand(self):
        self.orders = []

        response = self.client.get("/api/decisions")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"items": [], "proposed_reservation_totals": []})

    def test_optimised_mode_is_explicit_and_keeps_default_api_fields(self):
        need = self.orders[0]["needed_date"]
        self.orders = [
            order(i, Decimal("100.00"), baseline=price, logistics=0, needed_date=need)
            for i, price in enumerate((120, 120, 60), 1)
        ]
        self.offers = [offer(1, capacity=350, fixed=600)]
        self.offers[0].update(variable_delivery_per_kg=0, handling_cost=0)
        self.price_tiers = [
            {"offer_id": 1, "min_quantity_kg": quantity, "price_per_kg": price}
            for quantity, price in ((1, 105), (200, 90), (300, 88))
        ]
        self.allocations = [allocation(1, 2, "50.00", "reserved")]

        with patch.object(bridge_app, "evaluate_optimised_plan", side_effect=AssertionError("Opt-in required")):
            default = self.client.get("/api/decisions")
            self.assertEqual(default.status_code, 200)
            self.assertEqual(self.client.get("/api/decisions?grouping=other").get_json(), default.get_json())
        fixed_page = self.client.get("/")
        fixed = default.get_json()
        self.assertEqual(set(fixed), {"items", "proposed_reservation_totals"})
        self.assertEqual(len(fixed["items"]), 1)
        self.assertNotIn("group_id", fixed["items"][0])
        self.assertEqual(fixed["items"][0]["best"]["total_cost"], 27000)
        self.assertIn("Fixed-batch plan.", fixed_page.get_data(as_text=True))

        response = self.client.get("/api/decisions?grouping=optimised")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["planning_status"], "exact")
        self.assertIsNone(payload["fallback_reason"])
        group, baseline = payload["items"]
        self.assertEqual(group["order_ids"], [1, 2])
        self.assertEqual([share["proposed_cost"] for share in group["proposed_retailer_costs"]],
                         ["9300.00", "9300.00"])
        self.assertEqual(baseline["order_ids"], [3])
        self.assertEqual(baseline["procurement"], "baseline")
        self.assertEqual(baseline["proposed_retailer_costs"], [])
        self.assertEqual(payload["proposed_reservation_totals"], [
            {"offer_id": 1, "window_id": 1, "quantity_kg": "200.00"},
        ])

        dashboard = self.client.get("/?grouping=optimised")
        self.assertEqual(dashboard.status_code, 200)
        html = dashboard.get_data(as_text=True)
        self.assertEqual(html.count(">Exact within the model<"), 2)
        self.assertIn('<strong>R1</strong> <span class="muted">· Order IDs 1', html)
        self.assertIn('<strong>R2</strong> <span class="muted">· Order IDs 2', html)
        self.assertIn("Individual baseline procurement", html)
        self.assertEqual(html.count("<caption>Proposed retailer costs</caption>"), 1)

    def test_dashboard_and_api_report_configured_limit_fallback(self):
        default = self.client.get("/api/decisions").get_json()
        with patch.dict(bridge_app.app.config, GROUP_PLANNING_MAX_RETAILERS="0"):
            response = self.client.get("/api/decisions?grouping=optimised")
            dashboard = self.client.get("/?grouping=optimised")

        self.assertEqual(response.status_code, 200)
        fallback = response.get_json()
        self.assertEqual(fallback["planning_status"], "fallback")
        self.assertIn("retailer bundle limit of 0", fallback["fallback_reason"])
        self.assertEqual(fallback["proposed_reservation_totals"], default["proposed_reservation_totals"])
        self.assertEqual([row["order_ids"] for row in fallback["items"]], [[1], [2], [3]])
        self.assertEqual(dashboard.status_code, 200)
        html = dashboard.get_data(as_text=True)
        self.assertIn("Fixed-batch fallback.", html)
        self.assertIn("retailer bundle limit of 0", html)
        self.assertEqual(html.count(">Exact within the model<"), 1)

    def test_get_decisions_fails_safely_for_ambiguous_allocation_rows(self):
        reserved = allocation(1, 1, "100.00", "reserved")
        released = allocation(1, 1, "100.00", "released")
        unknown = allocation(1, 1, "100.00", "unknown")
        cases = [
            ([reserved, released], "Multiple allocation rows"),
            ([unknown], "Unrecognised allocation status"),
        ]
        for rows, expected_error in cases:
            with self.subTest(expected_error=expected_error):
                self.allocations = rows
                response = self.client.get("/api/decisions")

                self.assertEqual(response.status_code, 400)
                self.assertIn(expected_error, response.get_json()["error"])


if __name__ == "__main__":
    unittest.main()
