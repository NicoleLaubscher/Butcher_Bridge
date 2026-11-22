"""Run the browser workflows against a new, loopback-only Docker MySQL server."""

import argparse
import os
import subprocess
import sys
from contextlib import contextmanager
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from secrets import token_hex
from threading import Thread
from time import monotonic, sleep
from unittest.mock import patch

from playwright.sync_api import expect, sync_playwright
from werkzeug.serving import make_server

APP_DIR = Path(__file__).resolve().parents[1]
IMAGE = "mysql:8.0.44"


def docker(*args, env=None, sql=None):
    return subprocess.run(
        ["docker", *args], input=sql, env=env, text=True, capture_output=True,
        check=True, timeout=90,
    ).stdout.strip()


@contextmanager
def disposable_mysql():
    name = "bb-workflows-" + token_hex(6)
    root_password = token_hex(24)
    app_password = token_hex(24)
    container = docker(
        "run", "--detach", "--rm", "--name", name,
        "--publish", "127.0.0.1::3306", "--tmpfs", "/var/lib/mysql", "--env", "MYSQL_ROOT_PASSWORD",
        IMAGE, env={**os.environ, "MYSQL_ROOT_PASSWORD": root_password},
    )
    try:
        admin_env = {**os.environ, "MYSQL_PWD": root_password}
        admin = ("exec", "--env", "MYSQL_PWD", "-i", container, "mysql",
                 "--user=root", "--host=127.0.0.1", "--protocol=TCP", "--batch", "--skip-column-names")
        deadline = monotonic() + 55
        while True:
            try:
                server_uuid = docker(*admin, env=admin_env, sql="SELECT @@server_uuid;")
                break
            except subprocess.CalledProcessError:
                if monotonic() >= deadline:
                    raise RuntimeError("The fresh MySQL container did not become ready.") from None
                sleep(0.5)

        for filename in ("schema.sql", "seed.sql"):
            output = docker(*admin, "--show-warnings", env=admin_env, sql=(APP_DIR / "sql" / filename).read_text())
            if output:
                print(f"{filename} server notes: {output}")
        docker(*admin, env=admin_env, sql=(
            f"CREATE USER 'bridge_verifier'@'%' IDENTIFIED BY '{app_password}';"
            "GRANT SELECT, INSERT, UPDATE ON butcherbridge_final.* TO 'bridge_verifier'@'%';"
        ))
        address, port = docker("port", container, "3306/tcp").rsplit(":", 1)
        if address != "127.0.0.1":
            raise RuntimeError("Expected MySQL to be published only on loopback.")
        yield {
            "DB_HOST": address, "DB_PORT": port, "DB_NAME": "butcherbridge_final",
            "DB_USER": "bridge_verifier", "DB_PASSWORD": app_password, "DB_SSL_CA": "",
            "APP_ENV": "development", "SECRET_KEY": token_hex(24), "APP_PASSWORD": token_hex(24),
            "GROUP_PLANNING_MAX_RETAILERS": "8", "GROUP_PLANNING_MAX_QUOTE_EVALUATIONS": "5000",
            "GROUP_PLANNING_MAX_SEARCH_NODES": "100000",
        }, server_uuid
    finally:
        docker("stop", "--time", "5", container)


@contextmanager
def local_flask(app):
    with make_server("127.0.0.1", 0, app) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}"
        finally:
            server.shutdown()
            thread.join()


def create_test_catalog(transaction):
    """Create segregated catalog rows with dates relative to this run."""
    today = date.today()
    area = "Simulated Test Area"
    with transaction() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO products (name,specification) VALUES (%s,%s)",
                    ("Rubric test beef", "Simulated chilled boneless"))
        product_id = cur.lastrowid
        cur.execute("INSERT INTO suppliers (name,service_area) VALUES (%s,%s)", ("Rubric test supplier", area))
        supplier_id = cur.lastrowid
        retailers, windows = [], []
        for label in ("A", "B"):
            cur.execute("INSERT INTO retailers (name,area) VALUES (%s,%s)", (f"Rubric test retailer {label}", area))
            retailers.append(cur.lastrowid)
            cur.execute("INSERT INTO order_windows (label,closes_at) VALUES (%s,%s)",
                        (f"Rubric test window {label}", today + timedelta(days=7)))
            windows.append(cur.lastrowid)
    return product_id, supplier_id, area, retailers, windows, (today + timedelta(days=14)).isoformat()


def fill(form, **fields):
    for name, value in fields.items():
        field = form.locator(f'[name="{name}"]')
        if field.evaluate("(el) => el.tagName") == "SELECT":
            field.select_option(str(value))
        else:
            field.fill(str(value))


def submit(page, button, method, path, status):
    with page.expect_navigation(wait_until="domcontentloaded"), page.expect_response(
        lambda response: response.url.endswith(path) and response.request.method == method,
    ) as sent:
        button.click()
    response = sent.value
    assert response.status == status, (path, response.status)


def read(page, path):
    response = page.request.get(path)
    assert response.status == 200, (path, response.status, response.text())
    return response.json()


def record_screenshot(page, directory, filename):
    if directory is not None:
        page.screenshot(path=directory / filename, full_page=True, animations="disabled")


def verify_demand(page, url, query, catalog, screenshots):
    product_id, _, area, retailers, windows, needed = catalog
    orders = []
    for retailer, window, status, price in zip(retailers, windows, ("draft", "committed"), (120, 110), strict=True):
        page.goto(url + "/orders")
        form = page.locator("#order-form")
        fill(form, retailer_id=retailer, window_id=window, product_id=product_id, needed_date=needed,
             delivery_area=area, quantity_kg=100, baseline_price_per_kg=price, status=status,
             evidence_note="SIMULATED disposable database workflow")
        submit(page, form.get_by_role("button", name="Create order"), "POST", "/api/orders", 201)
        [stored] = query("SELECT id,status,quantity_kg FROM demand_orders WHERE product_id=%s AND window_id=%s",
                         (product_id, window))
        order_id = stored["id"]
        orders.append(order_id)
        row = page.get_by_role("row").filter(has=page.get_by_role("cell", name=str(order_id), exact=True))
        expect(row.get_by_role("cell", name=status, exact=True)).to_be_visible()
        assert (stored["status"], stored["quantity_kg"]) == (status, Decimal("100.00"))
        if status == "draft":
            assert not any(order_id in item["order_ids"] for item in read(
                page, url + "/api/decisions?grouping=optimised",
            )["items"])
            submit(page, row.get_by_role("button", name="Commit"), "PATCH", f"/api/orders/{order_id}", 200)
            expect(row.get_by_role("cell", name="committed", exact=True)).to_be_visible()
            assert query("SELECT status FROM demand_orders WHERE id=%s", (order_id,)) == [{"status": "committed"}]
    decisions = read(page, url + "/api/decisions?grouping=optimised")
    assert sorted(oid for row in decisions["items"] if row["product_id"] == product_id
                  for oid in row["order_ids"]) == sorted(orders)
    record_screenshot(page, screenshots, "01-simulated-demand.png")
    print("Flow 1 PASS | Browser POST 201, PATCH 200, persisted 100 kg orders and committed-only planning.")
    return orders


def verify_offers(page, url, query, catalog, screenshots):
    product_id, supplier_id, _, _, windows, _ = catalog
    page.goto(url + "/offers")
    form = page.locator("#offer-form")
    fill(form, supplier_id=supplier_id, product_id=product_id, capacity_kg=150, lead_days=2,
         fill_rate="0.98", fixed_delivery=100, variable_delivery_per_kg=1, handling_cost=25,
         tiers_text="1:90,100:80", evidence_note="SIMULATED disposable database workflow")
    submit(page, form.get_by_role("button", name="Create offer"), "POST", "/api/offers", 201)
    expect(page.get_by_role("cell", name="Rubric test supplier", exact=True)).to_be_visible()
    [stored] = query("SELECT id,capacity_kg FROM supplier_offers WHERE supplier_id=%s AND product_id=%s",
                     (supplier_id, product_id))
    offer_id = stored["id"]
    assert stored["capacity_kg"] == Decimal("150.00")
    tiers = query("SELECT min_quantity_kg,price_per_kg FROM price_tiers WHERE offer_id=%s ORDER BY min_quantity_kg",
                  (offer_id,))
    assert [(row["min_quantity_kg"], row["price_per_kg"]) for row in tiers] == [(1, 90), (100, 80)]
    for suffix in ("", "?grouping=optimised"):
        decision = read(page, url + "/api/decisions" + suffix)
        rows = [row for row in decision["items"] if row["product_id"] == product_id]
        assert len(rows) == 2 and all(row["offers"][0]["eligible"] for row in rows)
        selected = [row for row in rows if row["proposed_offer_id"] == offer_id]
        assert len(selected) == 1 and selected[0]["window_id"] == windows[0]
        assert selected[0]["best"]["total_cost"] == 8225
        assert {"offer_id": offer_id, "window_id": windows[0], "quantity_kg": "100.00"} in decision[
            "proposed_reservation_totals"
        ]
    comparison = read(page, url + "/api/decisions/comparison")
    assert comparison["fixed"]["planning_status"] == comparison["optimised"]["planning_status"] == "exact"
    assert query("SELECT COUNT(*) AS n FROM allocations WHERE offer_id=%s", (offer_id,)) == [{"n": 0}]
    page.goto(url + "/?grouping=optimised")
    expect(page.get_by_role("heading", name="Plan cost comparison")).to_be_visible()
    expect(page.get_by_role("link", name="Optimise retailer groups")).to_have_attribute("aria-current", "page")
    record_screenshot(page, screenshots, "02-simulated-comparison.png")

    reservation = {"offer_id": offer_id, "window_id": windows[0], "quantity_kg": "100.00"}
    assert page.request.post(url + "/api/allocations", data=reservation).status == 201
    assert page.request.post(url + "/api/allocations", data=dict(reservation, quantity_kg="1.00")).status == 409
    assert page.request.post(url + "/api/allocations", data=dict(
        reservation, window_id=windows[1], quantity_kg="51.00",
    )).status == 400
    assert query("SELECT quantity_kg FROM allocations WHERE offer_id=%s", (offer_id,)) == [
        {"quantity_kg": Decimal("100.00")}
    ]
    print("Flow 2 PASS | Offer and tiers persisted, both plans assign one 100 kg purchase at R8,225 "
          "against 150 kg capacity. GET created no hold. Booking 201, occupied key 409, excess capacity 400.")


def verify_fulfilment(page, url, query, order_id, screenshots):
    before = read(page, url + "/api/kpis")
    assert all(before[key] is None for key in ("fill_pct", "on_time_pct", "otif_pct"))
    page.goto(url + "/fulfilment")
    form = page.locator("#fulfil")
    fill(form, demand_order_id=order_id, delivered_kg=95, planned_days=2, actual_days=2,
         quoted_cost=8225, actual_cost=8300)
    submit(page, form.get_by_role("button", name="Save fulfilment"), "POST", "/api/fulfilments", 201)
    [stored] = query(
        "SELECT d.status, f.delivered_kg, f.actual_cost FROM fulfilments f "
        "JOIN demand_orders d ON d.id=f.demand_order_id WHERE d.id=%s", (order_id,),
    )
    assert (stored["status"], stored["delivered_kg"], stored["actual_cost"]) == (
        "fulfilled", Decimal("95.00"), Decimal("8300.00")
    )
    after = read(page, url + "/api/kpis")
    assert after == dict(before, committed_kg=before["committed_kg"] - 100,
                         fill_pct=95.0, on_time_pct=100.0, otif_pct=0.0)
    assert not any(order_id in row["order_ids"] for row in read(
        page, url + "/api/decisions?grouping=optimised",
    )["items"])
    expect(page.get_by_text("95.0%", exact=True)).to_be_visible()
    expect(page.get_by_text("100.0%", exact=True)).to_be_visible()
    expect(page.get_by_text("0.0%", exact=True)).to_be_visible()
    record_screenshot(page, screenshots, "03-simulated-fulfilment.png")
    print("Flow 3 PASS | Browser fulfilment 201, recorded 95 of 100 kg in 2 days. "
          "Persisted fulfilled state, fill 95%, on time 100%, strict OTIF 0%.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chromium-executable", help="Use a local Chromium binary instead of Playwright's build.")
    parser.add_argument("--screenshots", type=Path, help="Save simulated workflow captures to this local directory.")
    args = parser.parse_args()
    if args.screenshots:
        args.screenshots.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(APP_DIR))
    with disposable_mysql() as (config, expected_uuid), patch.dict(os.environ, config), patch("dotenv.load_dotenv"):
        from app import app
        from db import query, transaction

        [server] = query("SELECT @@server_uuid AS server_uuid, VERSION() AS version")
        if server["server_uuid"] != expected_uuid:
            raise RuntimeError("The app's connection does not target the fresh container.")
        tables = query("SELECT ENGINE AS engine FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE()")
        assert len(tables) == 9 and all(row["engine"] == "InnoDB" for row in tables)
        print(f"SIMULATED browser verification | MySQL {server['version']} | nine InnoDB tables")
        catalog = create_test_catalog(transaction)
        with local_flask(app) as url, sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=args.chromium_executable)
            try:
                page = browser.new_page(viewport={"width": 1280, "height": 900})
                page.set_default_timeout(8_000)
                page.goto(url + "/login")
                page.get_by_label("Password").fill(config["APP_PASSWORD"])
                page.get_by_role("button", name="Sign in").click()
                expect(page.get_by_role("heading", name="Procurement dashboard")).to_be_visible()
                orders = verify_demand(page, url, query, catalog, args.screenshots)
                verify_offers(page, url, query, catalog, args.screenshots)
                verify_fulfilment(page, url, query, orders[0], args.screenshots)
            finally:
                browser.close()


if __name__ == "__main__":
    main()
