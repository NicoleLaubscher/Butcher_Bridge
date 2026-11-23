# ButcherBridge API reference

Group 06 uses a signed Flask session for every `/api/` route. Send JSON objects with `Content-Type: application/json` for writes. The examples below use fictional data and IDs. Run write examples against a disposable test schema.

## Authentication and errors

`GET /login` serves the sign-in form. `POST /login` accepts form field `password` and redirects with HTTP 302 on success. An incorrect password renders the form with an error and HTTP 200. Keep the session cookie for subsequent requests. `POST /logout` clears the session and redirects to sign-in. These two form endpoints use HTML and redirects. The JSON API returns HTTP 401 with `{"error":"Sign in first"}` if the session is missing.

| Status | Meaning in the current application |
|---|---|
| 200 | Successful read or order update |
| 201 | Successful order, offer, reservation or fulfilment creation |
| 400 | Invalid JSON, input, query range or state rejected by a route |
| 401 | Sign-in required for an API route |
| 404 | Route or requested record unavailable, as described below |
| 405 | Unsupported method for an existing path. The `Allow` header lists supported methods. |
| 409 | Database integrity conflict, including certain duplicate and foreign-key failures |
| 500 | Unexpected failure, returned as a generic error |

Flask preserves Werkzeug HTTP statuses and headers. For example, `PUT /api/orders` returns HTTP 405 with `{"error":"Method Not Allowed"}` and the `Allow` header. Unknown routes return HTTP 404 with `{"error":"Route not found"}`. Database integrity errors log the exception type and return a generic HTTP 409. Unexpected failures log a traceback and return a generic HTTP 500. The current session shares one demonstration password across users. [Error handlers](../app.py#L363) · [Deployment limitations](DEPLOYMENT_GUIDE.md#operating-environment-and-limitations)

## Endpoint summary

| Method | Path | Purpose | Success | Database effect |
|---|---|---|---:|---|
| GET | `/api/orders` | Paginated order list and status filter | 200 | Read orders and retailer names |
| POST | `/api/orders` | Create demand in an open window | 201 | Insert order after locking/checking the window |
| GET | `/api/orders/<oid>` | Read one order by positive integer ID | 200 | Read order |
| PATCH | `/api/orders/<oid>` | Edit selected fields, commit or withdraw | 200 | Lock and update order |
| GET | `/api/offers` | List current offer records and supplier fields | 200 | Read offers and suppliers |
| POST | `/api/offers` | Create an offer with price tiers | 201 | Insert offer and tiers together |
| PATCH | `/api/offers/<offer_id>` | Update offer terms and optionally replace all price tiers | 200 | Lock offer, validate reserved capacity, update offer and tiers atomically |
| GET | `/api/decisions` | Fixed batches or `?grouping=optimised` | 200 | Read orders, offers, tiers and allocations |
| GET | `/api/decisions/comparison` | Compare costs on a single snapshot | 200 | Read the same inputs in one read-only transaction |
| GET | `/api/kpis` | Recorded orders, committed kg and actual fulfilment | 200 | Read demand and linked fulfilments |
| POST | `/api/allocations` | Confirm a capacity reservation for an offer/window | 201 | Lock offer, check remaining capacity, insert allocation |
| POST | `/api/fulfilments` | Record delivery for a committed order | 201 | Insert outcome and mark order fulfilled atomically |

Orders support create, list, detail and partial update. Offers support create, list and partial update. Allocation release, fulfilment correction and deletion endpoints are absent. The reference catalogs (retailers, products, suppliers and windows) are read by UI forms and have no management API.

## Orders

### GET /api/orders and GET /api/orders/&lt;oid&gt;

The list defaults to `page=1` and `size=20`, with page range 1–100,000 and page size 1–100. Use `status=draft|committed|withdrawn|fulfilled` or omit the filter. Records are ordered by decreasing ID. Pagination uses an offset and returns no total count or next-link. Invalid inputs return HTTP 400. An empty page returns HTTP 200 with an empty array.

Example empty result for `GET /api/orders?page=1&size=2&status=committed`.

```json
{"items":[],"page":1,"size":2}
```

Each list row has the same stored fields as the detail response plus `retailer_name`. Detail returns HTTP 404 for a missing ID. The following example shows `GET /api/orders/42`.

```json
{
  "id":42,"retailer_id":1,"product_id":1,"window_id":1,
  "needed_date":"Wed, 08 Dec 2027 00:00:00 GMT","delivery_area":"Soweto",
  "quantity_kg":"100.00","baseline_price_per_kg":"120.00","baseline_logistics_cost":"0.00",
  "baseline_trips":1,"baseline_distance_km":"0.00","status":"draft",
  "evidence_type":"simulated","evidence_note":"Fictional example",
  "created_at":"Wed, 01 Dec 2027 10:00:00 GMT","updated_at":"Wed, 01 Dec 2027 10:00:00 GMT"
}
```

### POST /api/orders

Required fields are `retailer_id`, `product_id`, `window_id` (existing positive integer IDs), `needed_date` (ISO date on or after server date), `delivery_area` (1–100 characters after trimming), and positive `quantity_kg`. Optional nonnegative fields are `baseline_price_per_kg`, `baseline_logistics_cost`, `baseline_distance_km` (default 0) and `baseline_trips` (whole trips, default 1). Use `status` of `draft` (default), `committed` or `withdrawn`. `evidence_type` accepts `primary`, `quoted`, `estimated` or `simulated` (default), and `evidence_note` is truncated at 500 characters. Verify baseline values against the evidence even when the API accepts a default.

```json
{"retailer_id":1,"product_id":1,"window_id":1,"needed_date":"2027-12-08","delivery_area":"Soweto","quantity_kg":"100.00","baseline_price_per_kg":"120.00","baseline_logistics_cost":"0.00","status":"draft","evidence_type":"simulated","evidence_note":"Fictional example"}
```

The window must exist, be open and have a closing date on or after the server date. The route checks calendar dates at day precision. An invalid window or input returns HTTP 400. Missing retailer/product relationships can return HTTP 409. For a successful creation the API returns the new ID.

```json
{"id":42,"message":"Order saved"}
```

### PATCH /api/orders/&lt;oid&gt;

Send a nonempty subset of `quantity_kg`, `baseline_price_per_kg`, `baseline_logistics_cost`, `status` or `evidence_note`. The same numeric/status rules apply. Changes to other fields require a separate administrative workflow. Invalid fields, fulfilled orders and closed/expired windows return HTTP 400. An unknown order returns HTTP 404. Only committed orders appear in procurement planning. A withdrawal does not release an allocation.

```json
{"status":"committed","quantity_kg":"100.00"}
```

```json
{"id":42,"message":"Order updated"}
```

## Offers and all-units tiers

`GET /api/offers` returns `items` in increasing offer ID order. No query filters or pagination are implemented. Each item includes the stored offer fields, `supplier_name` and `service_area`. The HTML offers page displays tiers from a separate SQL query. The GET API does not nest tier records.

```json
{"items":[{"id":4,"supplier_id":1,"product_id":1,"capacity_kg":"150.00","lead_days":2,"fill_rate":"0.9800","fixed_delivery":"100.00","variable_delivery_per_kg":"1.00","handling_cost":"25.00","coordinated_trips":1,"coordinated_distance_km":"0.00","active":1,"evidence_type":"simulated","evidence_note":"Fictional example","created_at":"Wed, 01 Dec 2027 10:00:00 GMT","updated_at":"Wed, 01 Dec 2027 10:00:00 GMT","supplier_name":"Supplier A","service_area":"Soweto"}]}
```

`POST /api/offers` requires positive `supplier_id`, `product_id`, `capacity_kg` and a `tiers` array of 1–20 records with distinct positive `min_quantity_kg` and nonnegative `price_per_kg`. Send nonnegative whole `lead_days`, a `fill_rate` fraction from 0 to 1, and optional nonnegative `fixed_delivery`, `variable_delivery_per_kg`, `handling_cost`, `coordinated_trips` and `coordinated_distance_km`. Defaults are zero except one coordinated trip and `active=1` from MySQL. Evidence fields follow the order rules. The HTML form converts comma-separated tiers into the structured JSON expected by the API.

`PATCH /api/offers/<offer_id>` accepts one or more of `capacity_kg`, `lead_days`, `fill_rate`, `fixed_delivery`, `variable_delivery_per_kg`, `handling_cost`, `coordinated_trips`, `coordinated_distance_km`, `active`, `evidence_type`, `evidence_note` and `tiers`. Numeric values are validated; lead days and coordinated trips must be whole numbers, fill rate must be between 0 and 1, and evidence type must be `primary`, `quoted`, `estimated` or `simulated`. If `tiers` is supplied, it replaces the full tier list and must contain 1–20 unique, positive quantity thresholds with nonnegative prices. The offer row is locked while it is updated; capacity cannot be reduced below currently reserved quantity. Offer changes and tier replacement commit together. Unknown offer IDs return 404; invalid values return 400.

```json
{"capacity_kg":"200.00","lead_days":3,"evidence_type":"quoted","evidence_note":"Supplier quote Q-14","tiers":[{"min_quantity_kg":"1.00","price_per_kg":"92.00"},{"min_quantity_kg":"100.00","price_per_kg":"81.50"}]}
```

```json
{"id":4,"message":"Offer updated"}
```

```json
{"supplier_id":1,"product_id":1,"capacity_kg":"150.00","lead_days":2,"fill_rate":"0.98","fixed_delivery":"100.00","variable_delivery_per_kg":"1.00","handling_cost":"25.00","evidence_type":"simulated","evidence_note":"Fictional example","tiers":[{"min_quantity_kg":"1.00","price_per_kg":"90.00"},{"min_quantity_kg":"100.00","price_per_kg":"80.00"}]}
```

Invalid or repeated thresholds and out-of-range fill return HTTP 400. Database integrity conflicts return HTTP 409. A failed tier insert rolls back the parent offer. For a successful creation the API returns the new ID.

```json
{"id":4,"message":"Offer and price tiers saved"}
```

## Decisions and capacity proposals

`GET /api/decisions` takes no body. The default returns fixed compatible batches as `items` and a sorted `proposed_reservation_totals` list. `grouping=optimised` adds the top-level `planning_status` and `fallback_reason`. Other `grouping` values select fixed mode. Optimised mode returns metadata for order/retailer IDs and compatibility buckets even when it falls back. The following example has an empty fixed response.

```json
{"items":[],"proposed_reservation_totals":[]}
```

| Decision field | Type and meaning |
|---|---|
| `window_id`, `product_id`, `needed_date`, `area` | Integer IDs and strings, with dates in `YYYY-MM-DD` |
| `orders`, `retailer_count`, `baseline_trips` | Integers |
| `quantity_kg`, `baseline_total`, `baseline_cost_per_kg`, `baseline_distance_km` | Legacy JSON numbers |
| `offers`, `best` | Quote array and one selected/diagnostic quote or null |
| `proposed_offer_id`, `decision`, `reason` | Selected offer ID or null, decision code and explanation |
| `savings_pct`, `recommended_savings_pct` | Quote diagnostic percent (nullable) and numeric percent for selected plan (0 for baseline) |
| `allocated_costs` | Legacy per-order rows with order ID, retailer and numeric cost. Can include diagnostic amounts. |
| `proposed_retailer_costs` | Selected proposal only. Each retailer has `retailer_id`, `retailer`, exact decimal strings `baseline_cap` and `proposed_cost`, and per-order `orders` with IDs and exact proposed costs. |
| `evidence_type` | `primary` if all included orders are primary, otherwise `mixed_or_simulated` |
| `group_id`, `retailer_ids`, `order_ids`, `source_bucket`, `procurement` | Optimised mode only. IDs and source window/product/date/area, with procurement `supplier` or `baseline`. |

Quote fields are `offer_id`, `supplier`, `eligible`, `reasons`, `total_cost`, `cost_per_kg`, `tier_min_kg`, `cost_sharing_reason`, `reserved_kg`, `available_kg`, `reservation_key_status`, `delivery_trips` and `distance_km`. Prices and tier threshold can be null when unpriced. Physical quote eligibility, key availability and fair cent-cost recovery are separate checks. Decisions include `ACCEPT`, `INDIVIDUAL_BETTER_QUOTE`, `INDIVIDUAL_KEEP_BASELINE`, `REJECT_NOT_CHEAPER`, `REJECT_NO_FEASIBLE_SUPPLIER` and `REJECT_PLANNING_LIMIT`. Use `proposed_offer_id` to identify a supplier assignment.

This simulated opt-in excerpt shows selected fields.

```json
{
  "planning_status":"exact","fallback_reason":null,
  "items":[{"group_id":"orders-1-2","retailer_ids":[1,2],"order_ids":[1,2],
            "source_bucket":{"window_id":1,"product_id":1,"needed_date":"2026-12-08","delivery_area":"Soweto"},
            "procurement":"supplier","proposed_offer_id":1,"decision":"ACCEPT"}],
  "proposed_reservation_totals":[{"offer_id":1,"window_id":1,"quantity_kg":"200.00"}]
}
```

The quantities in `proposed_reservation_totals` are exact decimal strings summed by offer/window key. This GET creates no holds. Only reserved rows consume capacity across all windows. Reserved and released rows both occupy the unique reservation key. A fallback contains a reason and the safe plan returned by the bounded solver. Invalid model data or grouping limit configuration can return HTTP 400. Runtime/database failures return HTTP 500.

### GET /api/decisions/comparison

No query parameters or request body. Returns both plan costs from the same materialised inputs and evaluation date. The database reads occur in one `REPEATABLE READ`, consistent, read-only InnoDB transaction. Baseline-retained orders contribute their full baseline. Costs are exact decimal strings. Percentage strings round half-up to two decimals. Zero denominators yield null. The fields `same_cost` and `same_assignments` have distinct meanings. Each plan has `exact` or `fallback` status and a nullable reason. Invalid model data returns HTTP 400 and unexpected reads or solver failures return HTTP 500.

```json
{
  "evaluated_on":"2026-11-19","committed_order_count":3,"baseline_total":"30000",
  "fixed":{"total_cost":"27000.00","savings_vs_baseline":"3000.00","savings_pct_of_baseline":"10.00","planning_status":"exact","fallback_reason":null},
  "optimised":{"total_cost":"24600.00","savings_vs_baseline":"5400.00","savings_pct_of_baseline":"18.00","planning_status":"exact","fallback_reason":null},
  "incremental":{"savings_vs_fixed":"2400.00","savings_pct_of_fixed":"8.89"},
  "same_cost":false,"same_assignments":false
}
```

## Reservations

`POST /api/allocations` requires positive integer `offer_id` and `window_id` and positive `quantity_kg`. It explicitly creates a new reserved row. The route locks an active offer, sums previous reserved kg and checks the quantity against shared capacity. Missing or inactive offer returns HTTP 404, invalid quantity or excess capacity returns HTTP 400, and a duplicate key or invalid foreign key can return HTTP 409. Capacity validation may reject a duplicate request before the unique constraint is reached. A client should review the plan and use the combined quantity for a key. The route does not re-evaluate recommendation economics or attach the hold to individual orders.

```json
{"offer_id":4,"window_id":1,"quantity_kg":"100.00"}
```

```json
{"message":"Capacity reserved"}
```

## Fulfilments and actual KPIs

`POST /api/fulfilments` takes a positive integer `demand_order_id`, nonnegative `delivered_kg`, `planned_days`, `actual_days`, positive `quoted_cost` and nonnegative `actual_cost`. Send all fields, with days as integers. The route defaults omitted nonnegative fields to zero. The order must exist (404 otherwise) and be committed. Delivery above ordered kg or an ineligible state, including normal repeat fulfilment, returns HTTP 400. An integrity conflict returns HTTP 409. Both the fulfilment row and order status update commit together.

```json
{"demand_order_id":42,"delivered_kg":"95.00","planned_days":2,"actual_days":2,"quoted_cost":"8225.00","actual_cost":"8300.00"}
```

```json
{"message":"Fulfilment saved"}
```

`GET /api/kpis` returns JSON numeric `orders` (all statuses), `committed_kg` (committed status only), `fill_pct`, `on_time_pct` and `otif_pct` (one decimal place or null when the denominator is zero). It uses recorded fulfilments joined to their orders. It applies no date window and reports no sample count. The example has one 95 kg delivery on a 100 kg order completed within the planned time.

```json
{"orders":1,"committed_kg":0.0,"fill_pct":95.0,"on_time_pct":100.0,"otif_pct":0.0}
```

## Data types and testing

Send fixed-scale money/quantity inputs as decimal strings and IDs/days/trips as whole integers. Current integer casts can truncate some numerics instead of rejecting them. Preserve DB DECIMAL strings and exact proposal/comparison strings when calculating totals. Decision item diagnostic fields and actual KPIs are legacy numbers. General database timestamps and the detail/list date are Flask HTTP-date strings. Decision `needed_date` and comparison `evaluated_on` are ISO date strings.

Local Bash example. Enter the password from private configuration. The temporary cookie jar is deleted when the shell exits.

```bash
bb_url=http://127.0.0.1:5000
bb_cookie=$(mktemp)
trap 'rm -f -- "$bb_cookie"' EXIT
read -rs -p 'Demo password: ' bb_password
printf '\n'
printf '%s' "$bb_password" | curl -fsS -c "$bb_cookie" --data-urlencode 'password@-' "$bb_url/login"
unset bb_password
curl -fsS -b "$bb_cookie" "$bb_url/api/orders?page=1&size=20&status=committed"
curl -fsS -b "$bb_cookie" "$bb_url/api/decisions?grouping=optimised"
curl -fsS -b "$bb_cookie" "$bb_url/api/decisions/comparison"
curl -fsS -b "$bb_cookie" "$bb_url/api/kpis"
```

In PowerShell, use an in-memory session.

```powershell
$bbUrl = 'http://127.0.0.1:5000'
$bbPassword = Read-Host 'Demo password' -AsSecureString
Invoke-WebRequest -Uri "$bbUrl/login" -Method Post -Body @{
    password = [pscredential]::new('demo', $bbPassword).GetNetworkCredential().Password
} -SessionVariable bbSession | Out-Null
Remove-Variable bbPassword
Invoke-RestMethod -Uri "$bbUrl/api/decisions/comparison" -WebSession $bbSession
```

See the [source routes](../app.py#L218), [workflow verification](END_TO_END_WORKFLOWS.md) and [API tests](../tests/test_api_contracts.py).
