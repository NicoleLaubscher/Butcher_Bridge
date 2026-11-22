# End-to-end workflow evidence

**Verified on 21 November 2026.** Three real Chromium form-to-Flask-to-MySQL flows passed on a new MySQL 8.0.44 Docker instance. All records and resulting KPIs were simulated. The browser used the actual forms, JavaScript, signed session cookie and application routes. The PyMySQL connection and transactions used nine real InnoDB tables. Separate mocked Flask tests cover HTTP inputs, failures and read-only behavior. A shared or hosted database was outside this verification.

The verification used Python 3.12.14 and Chromium 156. A fresh virtual environment installed the application requirements successfully, with Flask 3.1.3 and PyMySQL 1.2.4. The full local unit suites passed 120 tests, including four regression checks for HTTP error handling. The three browser flows ran separately. Tables, FKs and named indexes were checked against `information_schema` in another disposable bootstrap.

During finalisation, the same three browser scenarios passed on a fresh loopback-only MySQL 8.0.44 process with a temporary data directory. Docker's VFS driver ran out of space when starting a new container in this workspace. The Docker verifier remains the documented reproduction command.

## Reproduce in a disposable instance

Use a running Docker Engine or Docker Desktop in Linux-container mode and a Python 3.12 environment with the application requirements. Install Playwright as a test-only tool. It is separate from the app's runtime dependencies. These commands work from the repository root in PowerShell and Unix shells when the intended virtual environment is active.

```sh
python -m pip install -r final_app/requirements.txt
python -m pip install playwright
python -m playwright install chromium
python -B final_app/scripts/verify_mysql_workflows.py
```

On a machine with Chromium already installed, the verifier accepts `--chromium-executable` with its path. Pass `--screenshots` with an empty local output directory outside the repository if the submission needs captures. Output filenames are `01-simulated-demand.png`, `02-simulated-comparison.png` and `03-simulated-fulfilment.png`. Show the simulated label in the video and captions. The script saves screenshots after sign-in and leaves credentials out of its output.

The verifier starts its own `mysql:8.0.44` container with temporary storage, random test credentials and a loopback-only published port. It never loads a local `.env` or accepts an external DB target. It executes the unchanged schema and seed inside that container, verifies the app's server UUID matches, then adds a dedicated fictional product, supplier, retailers and windows. The app user has select, insert and update privileges on the test schema. It stops and removes only its own container when the run ends. Review any interrupted run by its `bb-workflows-` name before cleaning up.

## Verified flows

| Flow and persona | Actions in the browser | Flask/API and MySQL path | Visible and persisted evidence |
|---|---|---|---|
| 1. Retailer coordinator | Create a 100 kg draft on **Retailer demand**, inspect the row, click **Commit**, then create another committed 100 kg order in a different open window | POST `/api/orders` → locks/checks `order_windows` and inserts `demand_orders` (201). PATCH `/api/orders/<oid>` changes status (200). GET `/api/decisions?grouping=optimised` reads inputs. | Both 100.00 kg rows persisted. The draft appeared in the refreshed order table and was absent from planning. Both order IDs appeared exactly once in the simulated product's plan after commitment. |
| 2. Purchasing coordinator | Add a supplier offer with 150 kg capacity and tiers `1:90,100:80` via **Supplier offers**, then open both planning modes | POST `/api/offers` → atomic inserts into `supplier_offers` and `price_tiers` (201). GET decisions and comparison → reads quotes, windows, orders and holds. | The offer and both tiers persisted. Both 100 kg windows qualified individually, but each plan selected only the higher-saving one. Its delivered quote was R8,225 and the proposed hold was 100.00 kg. GET created no allocation. The optimised dashboard displayed its active mode and exact status. |
| 3. Fulfilment coordinator | Choose the first committed order, enter 95 kg delivered, 2 planned days, 2 actual days, R8,225 quoted and R8,300 actual | POST `/api/fulfilments` → locks order, inserts `fulfilments` and updates `demand_orders.status` to fulfilled (201). GET `/api/kpis` recalculates recorded outcomes. | Reloaded page showed **95.0% fill, 100.0% on time and 0.0% strict OTIF**. SQL confirmed the outcome and state. Committed kg fell by 100 and the fulfilled order left the plan. Previously all three fulfilment percentages were null. |

Flow 2 also exercised the separate confirmation endpoint using the browser's authenticated request context. `POST /api/allocations` returned 201 for 100 kg. A second 1 kg on the occupied key returned 409 and 51 kg on the other window returned 400 with only 50 kg left. SQL confirmed exactly one 100 kg reservation. The dashboard has advisory proposals and no reservation-confirmation form.

## Record the evidence

1. Record the Git SHA, Python/MySQL/browser versions, environment type and date. Save the verifier's outcome lines and selected screenshots from the simulated run. Keep secret values, cookies and real business records out of the recording.
2. On an authorised verification schema, select the fixture IDs shown in the UI, then query only the relevant rows. For example, replace `@order_id` and `@offer_id` with session variables set to authorised fixture IDs.

```sql
SELECT id, status, quantity_kg FROM demand_orders WHERE id = @order_id;
SELECT offer_id, min_quantity_kg, price_per_kg FROM price_tiers WHERE offer_id = @offer_id;
SELECT offer_id, window_id, status, quantity_kg FROM allocations WHERE offer_id = @offer_id;
SELECT demand_order_id, delivered_kg, planned_days, actual_days FROM fulfilments WHERE demand_order_id = @order_id;
```

3. Explain the difference between the observed test outcome and client impact. The recorded KPI change above is a database/UI integration check using fictional deliveries. The offline cost fixtures estimate procurement alternatives on matching inputs. Commercial savings require measured client evidence. [Offline comparison demo](../demo_comparison.py)

Observed tooling notes. The original seed completed with MySQL warning 1287 for deprecated `VALUES(col)` in upserts. Chromium requested a favicon that the app does not currently serve. The verification passed. Browser testing did not measure production traffic or exercise a hosted TLS deployment.
