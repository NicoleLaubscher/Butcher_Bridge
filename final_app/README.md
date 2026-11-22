# ButcherBridge — BFB321 Group 06

ButcherBridge helps local meat retailers compare individual procurement with compatible supplier purchases. The final application uses browser forms, Flask and PyMySQL to persist demand, offers, reservations and fulfilments. It compares fixed batches and optimised retailer groups on a common read snapshot and reports actual KPIs from recorded fulfilments. The original classroom simulator has a separate entry point at the repository root.

## Start the final application

Use Python 3.12 and MySQL 8.0 with InnoDB. Workbench is a client for creating and inspecting an approved schema. The versioned bootstrap targets `butcherbridge_final`. Use the fictional seed only on an empty disposable instance. For a verified reproduction of the three workflows without an existing database, run the [disposable MySQL verifier](docs/END_TO_END_WORKFLOWS.md#reproduce-in-a-disposable-instance).

Run these commands from `final_app/` in Windows PowerShell.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
.\.venv\Scripts\python.exe app.py
```

Configure the [environment template](.env.example) privately with the approved schema, restricted DB user, CA for hosted TLS and local sign-in/session secrets. Open `http://127.0.0.1:5000/login`. Use the [deployment guide](docs/DEPLOYMENT_GUIDE.md) for Unix setup, MySQL prerequisites, backup/restore, rollback, production limitations and both test commands. Keep live credentials, cookies and client records out of the repository and demonstration.

## Architecture and submission evidence

- Physical [database ERD](docs/diagrams/database_erd.svg), [system architecture](docs/diagrams/architecture.svg) and [decision workflow](docs/diagrams/decision_workflow.svg). Editable sources and rendering commands are in the [diagram guide](docs/diagrams/README.md).
- [Three verified end-to-end workflows](docs/END_TO_END_WORKFLOWS.md), including real browser/UI, API and MySQL persistence in a disposable test environment.
- [Rubric matrix](docs/RUBRIC_COMPLIANCE_MATRIX.md), [impact/KPI chart and table](docs/IMPACT_AND_KPIS.md) and [primary evidence protocol](docs/PRIMARY_DATA_COLLECTION.md).
- [Part C blueprint](docs/PART_C_REPORT_BLUEPRINT.md), [report evidence index](docs/REPORT_EVIDENCE_INDEX.md) and [5–8 minute demo outline](docs/DEMO_WALKTHROUGH.md).
- Group 06 roster and contribution evidence, including [observed GitHub accounts and pending confirmations](docs/TEAM_CONTRIBUTIONS_AUDIT.md). The root README documents the earlier classroom stage.

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

Read the [complete API reference](docs/API_DOCUMENTATION.md) for request/response examples, session and errors, validation and pagination.

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

## Operations and limitations

The app uses a shared demo password and server-side console logs. Hosting, individual authentication/authorisation, CSRF protection and operational monitoring are separate deployment decisions. The plan compares estimates, and bookings and fulfilments require explicit writes. For data protection, certificate handling, protected logs, isolated recovery tests and release rollback, use the [operations guide](docs/DEPLOYMENT_GUIDE.md#backup-restore-and-rollback). Report only verified evidence from the approved environment.
