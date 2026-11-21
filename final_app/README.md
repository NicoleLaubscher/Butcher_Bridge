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
| GET | `/api/decisions` | Baseline, feasibility, accept/reject, allocations |
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

## Reset, backup, collaboration and limitations

Before changing schema, take a provider snapshot or a `mysqldump --single-transaction --routines --triggers` database backup and test restoration in an isolated database. Never publish backups containing primary/commercially sensitive data. A destructive dev-only reset is `DROP DATABASE butcherbridge;` followed by schema and seed; use it **only** if every teammate agrees and the provider supports recreate.

Schema is version 1. For later database changes, create numbered SQL migrations; do not edit the shared schema silently. Query failures roll back changes and are logged to console. Prefer PRs with individual meaningful commits; review and test before merging.

**Not production-ready:** uses a group demo password rather than individual role-based authentication; no separate app-host deployment configured; route-distance is supplied evidence rather than automatic route optimisation; withdrawals after closing require manual review; reservation API is intentionally separated from the recommendation rather than automatic ordering; no physical cold-chain compliance verification. Add role-based authentication, audit permissions, CSRF protection and HTTPS before allowing public users. Current tests exercise decision rules only and do not constitute a live cloud MySQL end-to-end test. These are transparent limits for the final report.

See `docs/PRIMARY_DATA_COLLECTION.md`, `docs/VIDEO_SCRIPT_OUTLINE.md`, `docs/REPORT_STRUCTURE.md`.
