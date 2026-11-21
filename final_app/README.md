# ButcherBridge — BFB321 Group 06 final-exam development package

A clean integration layer for the original ButcherBridge semester demonstration. **Do not overwrite the original repository or its supply_chain_model.py** without a team review. This folder is an installable working starting point with Flask, a MySQL 8 schema, JSON APIs, forms, capacity reservations, live dashboard, and scenario tests.

## Shared database architecture (important)

MySQL Workbench 8.0 CE is a CLIENT, not a hosted server. Use **one remote managed MySQL 8-compatible server** reachable over TLS. Everyone uses their own Workbench connection and `.env` pointing at the same server/schema. No laptop needs to stay online. Railway's MySQL service is one possible provider; check current pricing, network access, backups and MySQL version before selecting. Do not put host credentials in GitHub. Never commit `.env`, exported real records or CA keys.

Cloud MySQL (one shared database) <--TLS--> Workbench on Nicole/Ruben/Symen computers
Cloud MySQL (one shared database) <--TLS--> Flask on each laptop (or deploy Flask to a host)

**Preferred for final demo:** deploy one Flask instance with HTTPS and demo password, using the same cloud database. For coursework development, running Flask on each laptop while all use the shared database is fine, but edits will affect all teammates, so use separate windows/scenario data IDs and coordinate resets.

## Setup in MySQL Workbench 8.0 CE

1. Create a hosted MySQL service in a group-controlled account. Give only the authorised group members access. Provider must support external MySQL TCP connectivity and TLS with a CA certificate. Confirm provider charges before creating a billable resource.
2. Each teammate opens Workbench -> home -> **+** under MySQL Connections. Select **Standard (TCP/IP)**. Enter the provider's hostname, port, username, and store the password securely. On the **SSL** tab choose **Require and Verify CA** or an equivalent verified setting, select the provider's downloaded CA. Click **Test Connection**. Do not disable certificate validation to bypass errors.
3. Provider creates an empty schema/database or grants CREATE DATABASE. In the SQL editor run `sql/schema.sql` with the lightning icon. If CREATE DATABASE is restricted, ask provider/admin to create database `butcherbridge`, then execute the script from `USE butcherbridge;` onwards.
4. Run `sql/seed.sql` **once** only on an empty schema. These values are simulated and must not be represented as primary data. Refresh the Schemas pane to see all tables; use Database -> Reverse Engineer to export an ERD matching the SQL.
5. Create a distinct *least-privilege* application DB user if provider supports it, and separate read-only accounts for learners who only need to view. Never use the root/admin user in Flask on a public server.

## Setup on each computer (PowerShell)

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe app.py
```

In `.env`: set the *same* shared DB_HOST/DB_PORT/DB_NAME for all teammates; DB_USER and DB_PASSWORD can be individual least-privilege credentials. Set DB_SSL_CA to an **existing local path to your provider CA file** (for Windows, `certs/provider-ca.pem` relative to the project). Set APP_PASSWORD and SECRET_KEY to random secrets. Never paste credentials into reports/screenshots/GitHub. Open `http://127.0.0.1:5000` and sign in using APP_PASSWORD.

## API (requires demo login session)

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/orders?page=1&size=20&status=committed` | List/paginate/filter |
| GET | `/api/orders/1` | Read one |
| POST | `/api/orders` | Create |
| PATCH | `/api/orders/1` | Update before window closes |
| GET | `/api/offers` | List offers |
| POST | `/api/offers` | Create offer and tiers |
| GET | `/api/decisions` | Read-only batch recommendations, quote comparisons and proposed reservation totals. |
| GET | `/api/decisions?grouping=optimised` | Opt-in retailer-group planning and explicit search status. |
| GET | `/api/decisions/comparison` | Read-only cost and status comparison of both plans on one snapshot. |
| GET | `/api/kpis` | Real DB KPI counts and actual fulfilment statistics |
| POST | `/api/allocations` | Reserve supplier capacity transactionally |
| POST | `/api/fulfilments` | Record completed order and update its status |

Example POST /api/orders JSON:
```
{"retailer_id":1,"product_id":1,"window_id":1,"needed_date":"2027-12-08","delivery_area":"Soweto","quantity_kg":100,"baseline_price_per_kg":95,"baseline_logistics_cost":600,"baseline_trips":1,"baseline_distance_km":25,"status":"committed","evidence_type":"simulated","evidence_note":"Class demo"}
```

POST /api/offers JSON:
```
{"supplier_id":1,"product_id":1,"capacity_kg":650,"lead_days":3,"fill_rate":0.98,"fixed_delivery":600,"variable_delivery_per_kg":1,"handling_cost":150,"coordinated_trips":1,"coordinated_distance_km":45,"evidence_type":"quoted","evidence_note":"Quotation ref (not a real quote yet)","tiers":[{"min_quantity_kg":1,"price_per_kg":95},{"min_quantity_kg":500,"price_per_kg":82}]}
```

See `/methodology` for explicit rules. Existing sample code's post-order functions remain in the original repository and are not deleted.

## Shared-capacity planning

The optimiser takes batches of committed orders with the same order window, product/specification ID, needed date and delivery area. Each batch can use its individual procurement baseline or an eligible supplier offer with a strictly lower delivered cost that can be shared within the retailer caps. The objective is to minimise the sum of these costs across batches.

Capacity is shared by offer ID across all windows. Every MySQL allocation with status `reserved` is deducted, including reservations in the batch's own window and windows outside the current demand. Reservation records identify an offer and window, so their full quantities are deducted before the planner considers new proposals.

If each batch's cheapest choice fits alongside the others, their sum gives the exact minimum. Otherwise the search counts combinations by multiplying the number of cheaper eligible offers plus one baseline choice for each batch. Conflicts above 100,000 combinations retain the baselines and return `REJECT_PLANNING_LIMIT` for batches that had cheaper eligible quotes.

In `items`, a quote's `reserved_kg` and `available_kg` are offer totals across all windows before applying any proposals. `eligible` describes the standalone supplier checks for capacity, service area, lead time, fill rate and price tier. `reservation_key_status` is `free`, `reserved` or `released` for the quote's offer and batch window. Both allocation statuses occupy the unique key, so only independently eligible quotes with a free key can be proposed for a new reservation.

`proposed_offer_id` identifies the supplier selected by the joint plan, or is `null` for baseline procurement. `recommended_savings_pct` compares the plan choice with the baseline and is zero when the batch keeps its baseline. `savings_pct` describes the displayed quotation for comparison.

`proposed_reservation_totals` is an array sorted by offer ID and window ID. It contains one entry per selected pair with `quantity_kg` as an exact decimal string without rounding or exponent notation. The total combines selected batch quantities for capacity only. Each batch retains its own price tier and delivery cost. An empty array means the plan made no new capacity proposals.

```json
[{"offer_id": 2, "window_id": 1, "quantity_kg": "400.30"}]
```

Free keys and proposed totals reflect the data read during evaluation. Existing holds require review because the schema records them at offer and window level. Duplicate allocation keys or unrecognised statuses return HTTP 400 with an explanation. Capacity reservations are recorded through a separate `POST /api/allocations` request that checks current capacity before writing.

## Retailer-group optimisation

Fixed batches remain the default on the dashboard and at `GET /api/decisions`. Choose **Optimise retailer groups** on the dashboard or request `GET /api/decisions?grouping=optimised` to opt in. All committed orders for a retailer within one compatibility bucket form one indivisible bundle. Each bundle appears in exactly one multi-retailer purchase, individual supplier purchase or individual baseline. The plan minimises the combined cost of those choices across all buckets, using the same feasibility, capacity, reservation and whole-cent cost-sharing rules as fixed batches.

The opt-in response adds `planning_status` and `fallback_reason`. A status of `exact` means the search proved the least-cost plan within the model and `fallback_reason` is `null`. A status of `fallback` gives the reason and returns a fresh fixed-batch plan for the complete set of orders. The fixed-batch planner keeps the baselines if its own limit is reached. Both opt-in statuses include `group_id` based on the sorted original order IDs, `retailer_ids`, `order_ids`, a `source_bucket` with the window, product, date and area, and `procurement` (`supplier` or `baseline`) on each item. `proposed_offer_id` identifies the selected offer and is `null` for baseline procurement.

The new search has three server-side limits. Set a nonnegative integer for each using its environment variable or the corresponding Flask config key.

| Setting | Default | What it bounds |
|---|---:|---|
| `GROUP_PLANNING_MAX_RETAILERS` | 8 | Retailer bundles in any one compatibility bucket |
| `GROUP_PLANNING_MAX_QUOTE_EVALUATIONS` | 5,000 | Subsets paired with active product-matching offers across the request, before the remaining quote checks |
| `GROUP_PLANNING_MAX_SEARCH_NODES` | 100,000 | Nodes visited in the exact search across all buckets |

Eight retailers can generate 255 nonempty subsets before assigning offers. The search processes bundles and ties in a stable order. When any limit is exceeded, the fixed-batch plan is the only result shown. Its status remains `fallback` even if it finds the best fixed-batch assignment.

`proposed_retailer_costs` and `proposed_reservation_totals` keep their existing formats. Each selected group is priced as a separate purchase with its own tier and delivery charge. Proposed capacity for groups sharing a free offer/window key is summed into one reservation total. Confirm that the supplier will honour the prices for separate purchases before booking. Decisions remain advisory and use the capacity and holds read for the request.

## Comparing the plans

The dashboard shows the two costs from one evaluation alongside the individual procurement baseline. Fixed batches remain the default detail view. The selector switches the detailed rows between plans. Details include retailer names and original order IDs, the kind of purchase or retained baseline, candidate quotes and proposed retailer charges.

The dashboard and signed-in `GET /api/decisions/comparison` read committed demand, offers, tiers and allocations in one MySQL `REPEATABLE READ` transaction with `WITH CONSISTENT SNAPSHOT, READ ONLY`. This assumes the application tables use InnoDB. The dashboard also reads its existing KPI inputs in that transaction. The connection is rolled back and closed after the reads and before planning. Both modes receive the same materialised inputs and the same evaluation date. A later request takes a fresh snapshot. The GET comparison neither books capacity nor writes orders or fulfilments.

Let **B** be total individual baseline, **F** the fixed-batch cost and **O** the optimised cost. Each plan covers every committed order ID once. A selected purchase contributes its delivered quote, rounded half-up to cents as in the decision engine. A retained baseline contributes the full unrounded sum of its order baselines. A diagnostic quote contributes no cost. The comparison calculates the following on exact Decimal totals.

| Measure | Amount | Percentage denominator |
|---|---:|---:|
| Fixed estimated saving | B − F | B |
| Optimised estimated saving | B − O | B |
| Incremental estimated saving from grouping | F − O | F |

The API supplies exact decimal strings for amounts and rounds percentages half-up to two decimal places. The dashboard keeps sub-cent digits when a baseline calculation produces them so the displayed amounts reconcile. Zero denominators return JSON `null` and display as a dash.

An `exact` plan is optimal within its model choices and constraints. `fallback` gives a reason and reports the cost of the returned plan. If the grouping search falls back to fixed batches, a zero difference provides no conclusion about better groupings. `same_cost` compares the totals. `same_assignments` compares the selected offer and original order IDs for each purchase, with all remaining orders assigned to baseline. Equal totals can arise from different assignments. Both legacy decision API responses keep their original fields.

### Reproduce the simulated results

From the repository root, run the following with Python 3.12. The script uses in-memory fixtures, the production planners and a fixed evaluation date. It requires neither a Flask session nor a MySQL connection. The fixtures are separate from `sql/seed.sql`.

```sh
python final_app/demo_comparison.py
```

| SIMULATED scenario | B | F | O | F − O |
|---|---:|---:|---:|---:|
| A and B buy together, C keeps its baseline | R30,000 | R27,000 | R24,600 | R2,400 |
| Two pairs buy from different offers | R48,000 | R36,600 | R35,500 | R1,100 |

The script prints which retailers and orders each purchase covers, the charges and savings for each retailer and the available capacity after existing holds. The fairness rule guarantees each proposed charge stays within that retailer's own baseline. Retailer C in the first scenario and C and D in the second still save more under the fixed plan. The scenarios show potential procurement savings under the model's supplied prices and constraints.

### Logistics inputs and recorded outcomes

Delivered cost uses the highest qualifying all-units price tier for the purchase quantity, plus one fixed delivery charge, the quantity times the variable per-kg delivery rate and one handling charge. Separate purchases on the same offer/window may therefore incur the fixed delivery and handling charges multiple times even though their proposed kg are combined for a capacity hold. The supplier must confirm pricing for these separate purchases.

Expected fill, lead days and service area determine quote eligibility. Remaining offer capacity is shared across dates and windows after active reservations. Released rows still occupy their offer/window key. Offer capacity describes the supply available for purchase. Vehicle payload, scheduling, routes, cold-chain compliance, fuel and emissions are outside the model. Baseline trips and distance are summed from the orders and coordinated trips and distance are descriptive fields from the offer. The baseline uses the recorded logistics cost directly.

Actual fill rate, on-time rate and strict on-time-in-full (OTIF) come from the recorded fulfilments. Actual fill is delivered kg divided by ordered kg for fulfilled records. On-time uses actual days at or below planned days. Strict OTIF also requires the full ordered quantity. These KPIs report recorded results. The comparison amounts are estimates from orders and quotes.

To validate the logistics inputs further, collect observed trip costs and payloads for one delivery lane and compare them with the current delivery charges.

## Proposed retailer costs

For each batch, the evaluator sums each retailer's order baselines (`kg × baseline price per kg + baseline logistics`) using `Decimal` and rounds the retailer's total down once to whole cents. That amount is the retailer's cap. A quote enters the joint planner only if it costs less than the combined unrounded baseline and its rounded total fits within the sum of the caps. Quotes that beat the raw baseline but exceed the caps carry a `cost_sharing_reason`. If none of the otherwise feasible supplier options can be shared within the caps at a saving, the batch keeps its baseline.

The selected quote is apportioned in proportion to the retailer caps, giving the same percentage saving against each positive cap before cent rounding. After assigning the whole-cent part of each share, any remaining cents go to the largest fractional remainders, with lower retailer IDs breaking ties. The charges sum to the exact quote and stay within the caps. A zero cap gets a zero charge. When all caps are zero, only a zero-cost quote can be fully allocated, and it still has to beat the combined unrounded baseline. Share sizes depend on reliable baseline evidence. For a fixed quote, understating a baseline can reduce that retailer's charge and shift cost to others.

Each decision item includes `proposed_retailer_costs` with one row per retailer ID for a selected proposal. The rows contain `retailer_id`, `retailer`, `baseline_cap`, `proposed_cost` and `orders`. The amounts are exact decimal strings with two fractional digits. Each `orders` entry has an `order_id` and its exact `proposed_cost`. A retailer's charge is apportioned to its orders by kg, with lower order IDs breaking rounding ties. The cap applies to the retailer total for the batch. The array is empty when the batch keeps its baseline.

`allocated_costs` retains the numeric per-order response fields. Its values reflect the retailer cost split for proposals. When a rejected quotation is retained for comparison, the field gives a diagnostic split by kg. Use the decimal strings in `proposed_retailer_costs` for exact cent reconciliation. The dashboard shows these proposed amounts as estimates.

## Reset, backup, collaboration and limitations

Before changing schema, take a provider snapshot or a `mysqldump --single-transaction --routines --triggers` database backup and test restoration in an isolated database. Never publish backups containing primary/commercially sensitive data. A destructive dev-only reset is `DROP DATABASE butcherbridge;` followed by schema and seed; use it **only** if every teammate agrees and the provider supports recreate.

Schema is version 1. For later database changes, create numbered SQL migrations; do not edit the shared schema silently. Query failures roll back changes and are logged to console. Prefer PRs with individual meaningful commits; review and test before merging.

**Not production-ready:** uses a group demo password rather than individual role-based authentication; no separate app-host deployment configured; route-distance is supplied evidence rather than automatic route optimisation; withdrawals after closing require manual review; reservation API is intentionally separated from the recommendation rather than automatic ordering; no physical cold-chain compliance verification. Add role-based authentication, audit permissions, CSRF protection and HTTPS before allowing public users. Tests exercise the decision rules and Flask routes with simulated data. These are transparent limits for the final report.

See `docs/PRIMARY_DATA_COLLECTION.md`, `docs/VIDEO_SCRIPT_OUTLINE.md`, `docs/REPORT_STRUCTURE.md`.
