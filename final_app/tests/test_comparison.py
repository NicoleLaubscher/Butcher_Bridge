"""Exact plan reconciliation and mocked read-only comparison route tests."""

import unittest
from collections import Counter
from contextlib import redirect_stdout
from datetime import date
from decimal import Decimal
from io import StringIO
from secrets import token_hex
from unittest.mock import MagicMock, call, patch

import decision_engine
from decision_engine import compare_plans, evaluate_plan
from demo_comparison import EVALUATED_ON, main, scenario_one, scenario_two
from group_formation_planner import GroupPlanningLimits
from test_decision_engine import offer, order, tiers

with patch("dotenv.load_dotenv"):
    import app as bridge_app


class TestPlanComparison(unittest.TestCase):
    def assert_reconciled(self, summary, plans, orders):
        expected_ids = Counter(row["id"] for row in orders if row["status"] == "committed")
        self.assertEqual(summary["committed_order_count"], sum(expected_ids.values()))
        for mode, rows in plans.items():
            with self.subTest(mode=mode):
                self.assertEqual(Counter(order_id for row in rows for order_id in row["order_ids"]), expected_ids)
                self.assertEqual(sum(row["planned_cost"] for row in rows), Decimal(summary[mode]["total_cost"]))
                for row in rows:
                    members = {m["retailer_id"]: m for m in row["retailers"]}
                    self.assertEqual(
                        sorted(oid for member in members.values() for oid in member["order_ids"]),
                        row["order_ids"],
                    )
                    shares = row["proposed_retailer_costs"]
                    if row["proposed_offer_id"] is None:
                        self.assertEqual(shares, [])
                        self.assertEqual(row["planned_cost"], sum(m["baseline"] for m in members.values()))
                        continue
                    self.assertEqual(sorted(s["retailer_id"] for s in shares), sorted(members))
                    self.assertEqual(sum(Decimal(s["proposed_cost"]) for s in shares), row["planned_cost"])
                    self.assertEqual(Decimal(str(row["best"]["total_cost"])), row["planned_cost"])
                    for share in shares:
                        member = members[share["retailer_id"]]
                        charge = Decimal(share["proposed_cost"])
                        self.assertGreaterEqual(charge, 0)
                        self.assertLessEqual(charge, Decimal(share["baseline_cap"]))
                        self.assertLessEqual(Decimal(share["baseline_cap"]), member["baseline"])
                        self.assertEqual([o["order_id"] for o in share["orders"]], member["order_ids"])
                        self.assertEqual(sum(Decimal(o["proposed_cost"]) for o in share["orders"]), charge)

    def assert_totals(self, summary, amounts, percentages):
        self.assertEqual(
            (summary["baseline_total"], summary["fixed"]["total_cost"], summary["optimised"]["total_cost"],
             summary["fixed"]["savings_vs_baseline"], summary["optimised"]["savings_vs_baseline"],
             summary["incremental"]["savings_vs_fixed"]),
            amounts,
        )
        self.assertEqual(
            (summary["fixed"]["savings_pct_of_baseline"], summary["optimised"]["savings_pct_of_baseline"],
             summary["incremental"]["savings_pct_of_fixed"]),
            percentages,
        )

    def test_first_simulated_scenario(self):
        inputs = scenario_one()
        summary, plans = compare_plans(*inputs, as_of=EVALUATED_ON)

        self.assert_totals(summary, ("30000", "27000.00", "24600.00", "3000.00", "5400.00", "2400.00"),
                           ("10.00", "18.00", "8.89"))
        self.assertEqual(summary["fixed"]["planning_status"], "exact")
        self.assertEqual(summary["optimised"]["planning_status"], "exact")
        fixed, = plans["fixed"]
        pair, retained = plans["optimised"]
        self.assertEqual((fixed["order_ids"], fixed["proposed_offer_id"]), ([1, 2, 3], 1))
        self.assertEqual((pair["order_ids"], pair["proposed_offer_id"]), ([1, 2], 1))
        self.assertEqual((retained["order_ids"], retained["proposed_offer_id"]), ([3], None))
        self.assertEqual(retained["planned_cost"], Decimal("6000"))
        self.assertEqual([share["proposed_cost"] for share in pair["proposed_retailer_costs"]],
                         ["9300.00", "9300.00"])
        self.assert_reconciled(summary, plans, inputs[0])

    def test_second_simulated_scenario_is_order_independent(self):
        inputs = scenario_two()
        summary, plans = compare_plans(*inputs, as_of=EVALUATED_ON)

        self.assert_totals(summary, ("48000", "36600.00", "35500.00", "11400.00", "12500.00", "1100.00"),
                           ("23.75", "26.04", "3.01"))
        self.assertEqual([(r["order_ids"], r["proposed_offer_id"], r["planned_cost"]) for r in plans["optimised"]],
                         [([1, 2], 1, Decimal("16500.00")), ([3, 4], 2, Decimal("19000.00"))])
        self.assertEqual((summary, plans), compare_plans(*(reversed(rows) for rows in inputs), as_of=EVALUATED_ON))
        self.assert_reconciled(summary, plans, inputs[0])

    def test_sub_cent_baselines_are_summed_before_any_display_rounding(self):
        orders = [
            order(1, Decimal("0.04"), baseline=Decimal("0.10"), logistics=0),
            order(2, Decimal("0.04"), baseline=Decimal("0.10"), logistics=0),
            order(3, status="draft"),
            order(4, status="withdrawn"),
            order(5, status="fulfilled"),
        ]
        summary, plans = compare_plans(orders, [], [], [], as_of=EVALUATED_ON)

        self.assert_totals(summary, ("0.0080", "0.0080", "0.0080", "0.0000", "0.0000", "0.0000"),
                           ("0.00", "0.00", "0.00"))
        self.assertEqual([row["baseline_total"] for row in plans["fixed"]], [0.01])
        self.assertEqual([row["baseline_total"] for row in plans["optimised"]], [0.0, 0.0])
        self.assertTrue(summary["same_cost"])
        self.assertTrue(summary["same_assignments"])
        self.assert_reconciled(summary, plans, orders)

    def test_quote_cents_survive_above_legacy_float_precision(self):
        orders = [order(1, Decimal("100000000.01"), baseline=Decimal("120000000.01"), logistics=0)]
        supplier = dict(offer(1, capacity=200000000, fixed=Decimal("0.05")),
                        variable_delivery_per_kg=0, handling_cost=0)
        summary, plans = compare_plans(orders, [supplier], tiers(price=Decimal("100000000.01")), [],
                                       as_of=EVALUATED_ON)

        self.assertEqual(summary["baseline_total"], "12000000002200000.0001")
        for mode, rows in plans.items():
            batch, = rows
            self.assertEqual(summary[mode]["total_cost"], "10000000002000000.05")
            self.assertEqual(batch["proposed_retailer_costs"][0]["proposed_cost"], summary[mode]["total_cost"])
            self.assertNotEqual(Decimal(str(batch["best"]["total_cost"])), batch["planned_cost"])

    def test_percentages_round_half_up(self):
        orders = [order(1, baseline=2, logistics=0)]
        supplier = dict(offer(1, fixed=Decimal("199.99")), variable_delivery_per_kg=0, handling_cost=0)
        summary, _ = compare_plans(orders, [supplier], tiers(price=0), [], as_of=EVALUATED_ON)

        self.assertEqual(summary["fixed"]["savings_vs_baseline"], "0.01")
        self.assertEqual(summary["fixed"]["savings_pct_of_baseline"], "0.01")

    def test_memberships_preserve_multiple_original_orders_per_retailer(self):
        inputs = scenario_one()
        orders = inputs[0]
        orders[0]["quantity_kg"] = 40
        orders.append(dict(orders[0], id=4, quantity_kg=60))
        summary, plans = compare_plans(*inputs, as_of=EVALUATED_ON)

        pair, _ = plans["optimised"]
        self.assertEqual(pair["order_ids"], [1, 2, 4])
        member = pair["retailers"][0]
        self.assertEqual(member["name"], "Retailer A")
        self.assertEqual(member["order_ids"], [1, 4])
        self.assertEqual([o["proposed_cost"] for o in pair["proposed_retailer_costs"][0]["orders"]],
                         ["3720.00", "5580.00"])
        self.assert_reconciled(summary, plans, orders)

    def test_zero_percentage_denominators(self):
        free_offer = dict(offer(1, fixed=0), handling_cost=0, variable_delivery_per_kg=0)
        cases = (
            ([], ("0", "0", "0", "0", "0", "0"), (None, None, None)),
            ([order(1, baseline=0, logistics=0)], ("0", "0", "0", "0", "0", "0"), (None, None, None)),
            ([order(1, baseline=1, logistics=0)], ("100", "0.00", "0.00", "100.00", "100.00", "0.00"),
             ("100.00", "100.00", None)),
        )
        for orders, amounts, percentages in cases:
            with self.subTest(amounts=amounts):
                summary, plans = compare_plans(orders, [free_offer], tiers(price=0), [], as_of=EVALUATED_ON)
                self.assert_totals(summary, amounts, percentages)
                self.assert_reconciled(summary, plans, orders)

    def test_diagnostic_quote_does_not_contribute_to_baseline_row_cost(self):
        orders = [order(1, baseline=70, logistics=0)]
        summary, plans = compare_plans(orders, [offer(1)], tiers(), [], as_of=EVALUATED_ON)

        fixed, = plans["fixed"]
        self.assertEqual(fixed["best"]["total_cost"], 9050.0)
        self.assertIsNone(fixed["proposed_offer_id"])
        self.assert_totals(summary, ("7000", "7000", "7000", "0", "0", "0"), ("0.00", "0.00", "0.00"))
        self.assert_reconciled(summary, plans, orders)

    def test_same_total_can_have_different_assignments(self):
        orders = [order(1, baseline=120, logistics=0), order(2, baseline=80, logistics=0),
                  order(3, baseline=120, logistics=0, window=2)]
        supplier = dict(offer(1, capacity=100, fixed=0), variable_delivery_per_kg=0, handling_cost=0)
        summary, plans = compare_plans(orders, [supplier], tiers(price=100), [], as_of=EVALUATED_ON)

        self.assertTrue(summary["same_cost"])
        self.assertFalse(summary["same_assignments"])
        self.assertEqual([r["order_ids"] for r in plans["fixed"] if r["proposed_offer_id"]], [[3]])
        self.assertEqual([r["order_ids"] for r in plans["optimised"] if r["proposed_offer_id"]], [[1]])
        self.assert_reconciled(summary, plans, orders)

    def test_grouping_fallback_independently_recomputes_the_fixed_plan(self):
        inputs = scenario_one()
        with patch.object(decision_engine, "evaluate_plan", wraps=evaluate_plan) as fixed:
            summary, plans = compare_plans(*inputs, as_of=EVALUATED_ON,
                                           limits=GroupPlanningLimits(max_retailers_per_bucket=2))

        self.assertEqual(fixed.call_count, 2)
        self.assertEqual(summary["fixed"]["planning_status"], "exact")
        self.assertEqual(summary["optimised"]["planning_status"], "fallback")
        self.assertIn("retailer bundle limit", summary["optimised"]["fallback_reason"])
        self.assertEqual(summary["incremental"], {"savings_vs_fixed": "0.00", "savings_pct_of_fixed": "0.00"})
        self.assertTrue(summary["same_assignments"])
        self.assertEqual(plans["fixed"], plans["optimised"])
        self.assert_reconciled(summary, plans, inputs[0])

    def test_fixed_limit_with_exact_grouping_or_with_both_falling_back(self):
        orders = [order(i, 400, window=i) for i in range(1, 18)]
        for limits, expected in ((GroupPlanningLimits(), "exact"),
                                 (GroupPlanningLimits(max_search_nodes=1), "fallback")):
            with self.subTest(expected=expected):
                summary, plans = compare_plans(orders, [offer(1)], tiers(), [], as_of=EVALUATED_ON, limits=limits)
                self.assertEqual(summary["fixed"]["planning_status"], "fallback")
                self.assertIn("joint planning limit", summary["fixed"]["fallback_reason"])
                self.assertEqual(summary["fixed"]["total_cost"], summary["baseline_total"])
                self.assertEqual(summary["optimised"]["planning_status"], expected)
                if expected == "fallback":
                    self.assertIn("fixed-batch planner also reached its limit", summary["optimised"]["fallback_reason"])
                    self.assertEqual(summary["optimised"]["total_cost"], summary["baseline_total"])
                    self.assertTrue(summary["same_assignments"])
                else:
                    self.assertEqual(Decimal(summary["incremental"]["savings_vs_fixed"]), Decimal("4650"))
                self.assert_reconciled(summary, plans, orders)

    def test_existing_holds_reduce_shared_capacity_and_both_statuses_occupy_keys(self):
        orders = [
            order(1, baseline=120, logistics=0, window=1),
            order(2, baseline=130, logistics=0, window=2),
            order(3, 50, baseline=200, logistics=0, window=3),
            order(4, 50, baseline=200, logistics=0, window=4),
        ]
        offers = [dict(offer(1, capacity=250, fixed=0), variable_delivery_per_kg=0, handling_cost=0)]
        holds = [{"offer_id": 1, "window_id": window, "quantity_kg": 100, "status": status}
                 for window, status in ((3, "reserved"), (4, "released"))]
        summary, plans = compare_plans(orders, offers, tiers(price=100), holds, as_of=EVALUATED_ON)

        self.assert_totals(summary, ("45000", "42000.00", "42000.00", "3000.00", "3000.00", "0.00"),
                           ("6.67", "6.67", "0.00"))
        for rows in plans.values():
            self.assertEqual([r["proposed_offer_id"] for r in rows], [None, 1, None, None])
            self.assertEqual([r["offers"][0]["available_kg"] for r in rows], [150] * 4)
            self.assertEqual([r["offers"][0]["reservation_key_status"] for r in rows],
                             ["free", "free", "reserved", "released"])
        self.assert_reconciled(summary, plans, orders)

    def test_separate_purchases_sharing_a_key_keep_their_own_tiers_and_fees(self):
        orders = [
            order(1, Decimal("0.10"), baseline=120, logistics=0),
            order(2, Decimal("0.20"), baseline=120, logistics=0, needed_date="2026-12-09"),
        ]
        offers = [dict(offer(1, capacity=Decimal("0.30"), fixed=Decimal("0.50")), handling_cost=Decimal("0.25"))]
        prices = [{"offer_id": 1, "min_quantity_kg": Decimal(qty), "price_per_kg": price}
                  for qty, price in (("0.01", 82), ("0.20", 80))]
        summary, plans = compare_plans(orders, offers, prices, [], as_of=EVALUATED_ON)

        _, holds = evaluate_plan(orders, offers, prices, [], as_of=EVALUATED_ON)
        self.assertEqual(holds, {(1, 1): Decimal("0.30")})
        self.assertEqual(summary["fixed"]["total_cost"], "26.00")
        for rows in plans.values():
            self.assertEqual([r["planned_cost"] for r in rows], [Decimal("9.05"), Decimal("16.95")])
        self.assert_reconciled(summary, plans, orders)

    def test_rejects_missing_or_duplicate_plan_coverage(self):
        for bad_ids in ([1, 2], [1, 1, 3]):
            def invalid_fixed(*args, **kwargs):
                rows, totals = evaluate_plan(*args, **kwargs)
                rows[0]["order_ids"] = bad_ids
                return rows, totals

            with self.subTest(bad_ids=bad_ids), patch.object(decision_engine, "evaluate_plan", invalid_fixed):
                with self.assertRaisesRegex(RuntimeError, "each committed order exactly once"):
                    compare_plans(*scenario_one(), as_of=EVALUATED_ON)

    def test_offline_demo_prints_the_calculated_assignments_costs_and_capacity(self):
        output = StringIO()
        with patch("db.connection", side_effect=AssertionError("Offline demo reached MySQL")), redirect_stdout(output):
            main()

        report = output.getvalue()
        self.assertEqual(report.count("SIMULATED scenario"), 2)
        self.assertIn("Individual baseline procurement | orders [3] | R6000.00", report)
        self.assertIn("Offer 1 capacity | 50 kg reserved + 200 kg proposed of 250 kg | PASS", report)
        self.assertIn("fairness PASS", report)
        self.assertNotIn("FAIL", report)
        self.assertIn("Incremental estimated savings R2400.00 (8.89% of fixed plan cost)", report)
        self.assertIn("Incremental estimated savings R1100.00 (3.01% of fixed plan cost)", report)


class TestComparisonRoutes(unittest.TestCase):
    def setUp(self):
        self.orders, self.offers, self.prices, self.holds = scenario_one()
        self.conn = MagicMock()
        self.conn.commit.side_effect = AssertionError("Comparison committed a database transaction")
        self.cursor = self.conn.cursor.return_value.__enter__.return_value
        self.cursor.execute.side_effect = self.execute_snapshot
        self.cursor.fetchall.side_effect = lambda: self.read_rows(self.sql)
        self.connect = self.enterContext(patch("db.connection", return_value=self.conn))
        self.enterContext(patch("db.pymysql.connect", side_effect=AssertionError("Live MySQL access")))
        self.enterContext(patch.object(bridge_app, "transaction", side_effect=AssertionError("Write route invoked")))
        self.query = self.enterContext(patch.object(bridge_app, "query", side_effect=self.read_rows))
        self.clock = self.enterContext(patch.object(bridge_app, "date", wraps=date))
        self.clock.today.return_value = EVALUATED_ON
        self.enterContext(patch.dict(bridge_app.app.config, TESTING=True, SECRET_KEY=token_hex(16),
                                     SESSION_COOKIE_SECURE=False))
        self.client = bridge_app.app.test_client()
        with self.client.session_transaction() as session:
            session["signed_in"] = True

    def execute_snapshot(self, sql):
        if sql in ("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ",
                   "START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY"):
            return
        self.assertTrue(sql.startswith("SELECT "))
        self.assertNotIn("FOR UPDATE", sql.upper())
        self.sql = sql

    def read_rows(self, sql):
        if sql.startswith("SELECT d.*"):
            return self.orders
        if sql.startswith("SELECT o.*"):
            return self.offers
        if "FROM price_tiers" in sql:
            return self.prices
        if "FROM allocations" in sql:
            return self.holds
        if "AS order_count" in sql:
            return [{"order_count": len(self.orders), "committed_kg": Decimal("300")}]
        if "FROM fulfilments" in sql:
            return [{"n": 2, "ordered": Decimal("100"), "delivered": Decimal("90"), "on_time": 2, "otif": 1}]
        self.fail(f"Unexpected read: {sql}")

    def test_comparison_consumes_one_read_only_snapshot_and_one_date(self):
        def check_closed(*inputs, **kwargs):
            self.conn.rollback.assert_called_once_with()
            self.conn.close.assert_called_once_with()
            self.assertTrue(all(isinstance(rows, tuple) for rows in inputs))
            return compare_plans(*inputs, **kwargs)

        with patch.object(bridge_app, "compare_plans", side_effect=check_closed), \
                patch.object(decision_engine, "evaluate_plan", wraps=evaluate_plan) as fixed, \
                patch.object(decision_engine, "evaluate_optimised_plan",
                             wraps=decision_engine.evaluate_optimised_plan) as optimised:
            response = self.client.get("/api/decisions/comparison")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["evaluated_on"], EVALUATED_ON.isoformat())
        self.assertEqual(payload["baseline_total"], "30000")
        self.assertEqual(payload["fixed"]["total_cost"], "27000.00")
        self.assertEqual(payload["optimised"]["total_cost"], "24600.00")
        self.assertEqual(payload["incremental"], {"savings_vs_fixed": "2400.00", "savings_pct_of_fixed": "8.89"})
        self.clock.today.assert_called_once_with()
        for argument, (fixed_arg, opt_arg) in enumerate(zip(fixed.call_args.args[:4], optimised.call_args.args[:4])):
            with self.subTest(argument=argument):
                self.assertIs(fixed_arg, opt_arg)
        self.assertIs(fixed.call_args.kwargs["as_of"], EVALUATED_ON)
        self.assertIs(optimised.call_args.kwargs["as_of"], EVALUATED_ON)
        self.connect.assert_called_once_with()
        self.conn.cursor.assert_called_once_with()
        self.assertEqual(self.cursor.execute.call_args_list, [
            call("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"),
            call("START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY"),
            call(bridge_app.ORDER_DETAILS + " WHERE d.status='committed' ORDER BY d.id DESC"),
            call(bridge_app.OFFER_DETAILS),
            call(bridge_app.PRICE_TIERS),
            call(bridge_app.ALLOCATIONS),
        ])
        self.assertEqual(self.cursor.fetchall.call_count, 4)
        self.conn.commit.assert_not_called()
        self.query.assert_not_called()

    def test_snapshot_error_returns_no_plan_and_releases_the_connection(self):
        def fail_read(sql):
            if "FROM price_tiers" in sql:
                raise RuntimeError("Fixture read failure")
            self.execute_snapshot(sql)

        self.cursor.execute.side_effect = fail_read
        with patch.object(bridge_app, "compare_plans") as plan, patch.object(bridge_app.app.logger, "exception"):
            response = self.client.get("/api/decisions/comparison")

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.get_json(), {"error": "Internal server error; see server logs"})
        self.conn.rollback.assert_called_once_with()
        self.conn.close.assert_called_once_with()
        self.conn.commit.assert_not_called()
        plan.assert_not_called()

    def test_comparison_requires_sign_in(self):
        self.assertEqual(bridge_app.app.test_client().get("/api/decisions/comparison").status_code, 401)
        self.connect.assert_not_called()

    def test_both_dashboards_show_the_comparison_and_active_memberships(self):
        fixed = self.client.get("/")
        optimised = self.client.get("/?grouping=optimised")

        for response in (fixed, optimised):
            self.assertEqual(response.status_code, 200)
            page = response.get_data(as_text=True)
            for text in ("R30,000.00", "R27,000.00", "R24,600.00", "R2,400.00", "8.89%",
                         "of the fixed-batch plan cost", "Actual fill rate", "90.0%",
                         "Supplier quotes and delivered cost", "Proposed retailer costs", "mixed_or_simulated"):
                self.assertIn(text, page)
            self.assertEqual(page.count('aria-current="page"'), 1)
        fixed_page, optimised_page = fixed.get_data(as_text=True), optimised.get_data(as_text=True)
        self.assertIn('<a href="/" aria-current="page">Fixed batches</a>', fixed_page)
        self.assertIn('<a href="/?grouping=optimised" aria-current="page">Optimise retailer groups</a>', optimised_page)
        self.assertEqual(fixed_page.count('class="panel procurement-batch"'), 1)
        self.assertEqual(optimised_page.count('class="panel procurement-batch"'), 2)
        self.assertIn("Supplier group", optimised_page)
        self.assertIn("Individual baseline procurement", optimised_page)
        self.assertIn('<strong>Retailer C</strong> <span class="muted">· Order IDs 3', optimised_page)
        self.assertEqual(self.connect.call_count, 2)
        self.assertEqual(self.cursor.fetchall.call_count, 12)
        self.conn.commit.assert_not_called()
        self.query.assert_not_called()

    def test_dashboard_fallback_explains_the_zero_increment(self):
        with patch.dict(bridge_app.app.config, GROUP_PLANNING_MAX_RETAILERS=2):
            response = self.client.get("/?grouping=optimised")

        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertEqual(page.count(">Exact within the model<"), 1)
        self.assertIn(">Fallback<", page)
        self.assertIn("retailer bundle limit of 2", page)
        self.assertIn("Better groupings may still exist.", page)

    def test_methodology_distinguishes_logistics_model_and_actual_outcomes(self):
        response = self.client.get("/methodology")

        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        for text in ("highest qualifying all-units tier", "own fixed delivery and handling charges",
                     "descriptive fields", "Actual fill", "recorded fulfilments", "use the fixed cost as the denominator"):
            self.assertIn(text, page)
        self.connect.assert_not_called()
        self.query.assert_not_called()


if __name__ == "__main__":
    unittest.main()
