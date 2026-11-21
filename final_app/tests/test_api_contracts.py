"""Focused API error, pagination and safe form presentation checks."""

import unittest
from contextlib import nullcontext
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from secrets import token_hex
from unittest.mock import MagicMock, patch

from pymysql.err import IntegrityError

with patch("dotenv.load_dotenv"):
    import app as bridge


class ApiContractsTest(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict(bridge.app.config, SECRET_KEY=token_hex(16),
                                     TESTING=True, SESSION_COOKIE_SECURE=False))
        self.enterContext(patch("db.connection", side_effect=AssertionError("Live MySQL access")))
        self.query = self.enterContext(patch.object(bridge, "query", side_effect=AssertionError("Unexpected SQL read")))
        self.write = self.enterContext(patch.object(bridge, "transaction",
                                                    side_effect=AssertionError("Unexpected SQL write")))
        self.client = bridge.app.test_client()
        with self.client.session_transaction() as session:
            session["signed_in"] = True

    def test_each_api_route_blocks_unauthenticated_requests_before_database_access(self):
        client = bridge.app.test_client()
        for rule in bridge.app.url_map.iter_rules():
            if not rule.rule.startswith("/api/"):
                continue
            path = rule.rule.replace("<int:oid>", "1")
            for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
                with self.subTest(path=path, method=method):
                    result = client.open(path, method=method)
                    self.assertEqual(result.status_code, 401)
                    self.assertEqual(result.get_json(), {"error": "Sign in first"})
        self.query.assert_not_called()
        self.write.assert_not_called()

    def test_unsupported_method_preserves_405_and_allowed_methods(self):
        with patch.object(bridge.app.logger, "exception") as unexpected_error:
            response = self.client.put("/api/orders", json={})
            page_response = self.client.put("/orders")
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.get_json(), {"error": "Method Not Allowed"})
        self.assertEqual(set(response.headers["Allow"].split(", ")), {"GET", "HEAD", "OPTIONS", "POST"})
        self.assertEqual(page_response.status_code, 405)
        self.assertEqual(page_response.mimetype, "text/html")
        self.assertEqual(set(page_response.headers["Allow"].split(", ")), {"GET", "HEAD", "OPTIONS"})
        unexpected_error.assert_not_called()
        self.query.assert_not_called()
        self.write.assert_not_called()

    def test_unknown_api_route_is_json_404(self):
        result = self.client.get("/api/nonexistent-route")
        self.assertEqual(result.status_code, 404)
        self.assertEqual(result.get_json(), {"error": "Route not found"})
        self.query.assert_not_called()
        self.write.assert_not_called()

    def test_invalid_order_quantity_keeps_validation_response(self):
        result = self.client.post("/api/orders", json={
            "retailer_id": 1, "product_id": 1, "window_id": 1,
            "needed_date": (date.today() + timedelta(days=1)).isoformat(),
            "delivery_area": "Test area", "quantity_kg": "0.00",
        })
        self.assertEqual(result.status_code, 400)
        self.assertEqual(result.get_json(), {"error": "quantity_kg must be positive"})
        self.write.assert_not_called()

    def test_internal_failure_is_logged_and_returns_generic_json_500(self):
        detail = "simulated internal database detail"
        self.query.side_effect = RuntimeError(detail)
        with self.assertLogs(bridge.app.logger, level="ERROR") as logs:
            result = self.client.get("/api/orders")
        self.assertEqual(result.status_code, 500)
        self.assertEqual(result.get_json(), {"error": "Internal server error; see server logs"})
        self.assertNotIn(detail, result.get_data(as_text=True))
        self.assertIn(f"RuntimeError: {detail}", "\n".join(logs.output))

    def test_order_list_uses_bound_status_and_requested_offset(self):
        self.query.side_effect = None
        self.query.return_value = [{"id": 5, "quantity_kg": Decimal("125.50"), "status": "committed"}]
        result = self.client.get("/api/orders?page=3&size=4&status=committed")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.get_json(), {
            "page": 3, "size": 4,
            "items": [{"id": 5, "quantity_kg": "125.50", "status": "committed"}],
        })
        sql, params = self.query.call_args.args
        self.assertIn("WHERE d.status=%s", sql)
        self.assertIn("ORDER BY d.id DESC LIMIT %s OFFSET %s", sql)
        self.assertEqual(params, ["committed", 4, 8])

    def test_invalid_order_list_arguments_are_rejected_before_query(self):
        for query in ("page=0", "page=100001", "page=abc", "size=101", "size=0", "status=reserved"):
            with self.subTest(query=query):
                result = self.client.get("/api/orders?" + query)
                self.assertEqual(result.status_code, 400)
                self.assertIn("error", result.get_json())
        self.query.assert_not_called()

    def test_order_detail_missing_id_is_404(self):
        self.query.side_effect = None
        self.query.return_value = []
        result = self.client.get("/api/orders/8")
        self.assertEqual(result.status_code, 404)
        self.assertEqual(result.get_json(), {"error": "Order not found"})
        self.assertEqual(self.query.call_args.args[1], (8,))

    def test_non_object_write_bodies_are_rejected_before_transactions(self):
        for path in ("/api/orders", "/api/offers", "/api/allocations", "/api/fulfilments"):
            with self.subTest(path=path):
                result = self.client.post(path, json=[])
                self.assertEqual(result.status_code, 400)
                self.assertEqual(result.get_json(), {"error": "Expected a JSON object"})
        self.write.assert_not_called()

    def test_offer_duplicate_decimal_threshold_is_rejected(self):
        result = self.client.post("/api/offers", json={
            "supplier_id": 1, "product_id": 1, "capacity_kg": "150.00", "fill_rate": "0.98",
            "tiers": [
                {"min_quantity_kg": "100", "price_per_kg": "85.00"},
                {"min_quantity_kg": "100.00", "price_per_kg": "80.00"},
            ],
        })
        self.assertEqual(result.status_code, 400)
        self.assertEqual(result.get_json(), {"error": "Duplicate price tier threshold"})
        self.write.assert_not_called()

    def test_unsupported_order_changes_are_rejected_before_write(self):
        for payload in ({"retailer_id": 2}, {"status": "fulfilled"}, {"quantity_kg": "NaN"}, {}):
            with self.subTest(payload=payload):
                result = self.client.patch("/api/orders/1", json=payload)
                self.assertEqual(result.status_code, 400)
        self.write.assert_not_called()

    def test_excess_delivery_rejected_after_locked_lookup_without_insert(self):
        conn = MagicMock()
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = {"status": "committed", "quantity_kg": Decimal("100.00")}
        self.write.side_effect = None
        self.write.return_value = nullcontext(conn)
        result = self.client.post("/api/fulfilments", json={
            "demand_order_id": 1, "delivered_kg": "100.01", "quoted_cost": "8225.00",
        })
        self.assertEqual(result.status_code, 400)
        self.assertEqual(result.get_json(), {"error": "Delivered quantity cannot exceed ordered quantity"})
        cursor.execute.assert_called_once()
        self.assertIn("FOR UPDATE", cursor.execute.call_args.args[0])

    def test_integrity_conflicts_return_safe_409(self):
        self.write.side_effect = IntegrityError(1062, "simulated private database detail")
        with self.assertLogs(bridge.app.logger, level="WARNING") as logs:
            result = self.client.post("/api/allocations", json={"offer_id": 1, "window_id": 1, "quantity_kg": 10})
        self.assertEqual(result.status_code, 409)
        self.assertIn("Duplicate or invalid related record", result.get_json()["error"])
        self.assertNotIn("simulated private database detail", result.get_data(as_text=True) + " ".join(logs.output))

    def test_order_page_does_not_offer_edits_for_fulfilled_or_expired_orders(self):
        now = datetime.combine(date.today(), time(12))
        windows = [
            {"id": 1, "label": "Valid window", "status": "open", "closes_at": now + timedelta(days=1)},
            {"id": 2, "label": "Expired option", "status": "open", "closes_at": now - timedelta(days=1)},
        ]
        orders = [
            {"id": 11, "status": "draft", "window_id": 1},
            {"id": 12, "status": "fulfilled", "window_id": 1},
            {"id": 13, "status": "committed", "window_id": 2},
        ]
        with patch.object(bridge, "lookup_data", return_value={
            "retailers": [{"id": 1, "name": "Simulated retailer"}],
            "products": [{"id": 1, "name": "Test product", "specification": "Test spec"}],
            "windows": windows,
        }), patch.object(bridge, "all_orders", return_value=orders):
            result = self.client.get("/orders")
        self.assertEqual(result.status_code, 200)
        html = result.get_data(as_text=True)
        self.assertIn('value="1">Valid window', html)
        self.assertNotIn("Expired option", html)
        self.assertIn("changeStatus(11,'committed')", html)
        self.assertNotIn("changeStatus(12,", html)
        self.assertNotIn("changeStatus(13,", html)

    def test_fulfilment_page_shows_no_sample_and_disabled_submit(self):
        self.query.side_effect = None
        self.query.return_value = []
        with patch.object(bridge, "dashboard_metrics", return_value={
            "fill_pct": None, "on_time_pct": None, "otif_pct": None,
        }):
            result = self.client.get("/fulfilment")
        self.assertEqual(result.status_code, 200)
        html = result.get_data(as_text=True)
        self.assertIn("<button disabled>Save fulfilment", html)
        self.assertIn("No committed orders", html)
        self.assertNotIn("—%", html)


if __name__ == "__main__":
    unittest.main()
