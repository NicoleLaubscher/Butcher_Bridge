# Deployment and operations handover

## 1. Obtain the release

```sh
git clone --branch feature/mysql-integration --single-branch https://github.com/NicoleLaubscher/Butcher_Bridge.git
cd Butcher_Bridge
git rev-parse HEAD
```

Record the approved SHA in submission and deployment evidence. The original classroom demo at the repository root and the final application under `final_app/` are independent entry points. Use `final_app/app.py` for Flask/MySQL and `run_butcherbridge_demo.py` for the earlier simulator. The final app has routes in `app.py`, PyMySQL connection/transaction helpers in `db.py`, separate calculation and bounded planner modules, Jinja `templates/`, `static/` CSS, `sql/`, `tests/` and this documentation.

## 2. Install the application

Use Python 3.12 and a MySQL 8.0 server with InnoDB and enforced CHECK constraints. MySQL 8.0.16 or later enforces these checks. The coursework verification targets 8.0.44. Workbench 8.0 CE is an administrative client. For team use, each reviewer connects with their own credentials to the approved managed server. Choose and budget hosting separately.

Run these PowerShell commands from the repository root.

```powershell
Set-Location final_app
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
.\.venv\Scripts\python.exe app.py
```

On Linux or macOS, run these commands from the repository root.

```bash
cd final_app
python3.12 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
test -e .env || cp .env.example .env
${EDITOR:-vi} .env
./.venv/bin/python app.py
```

The commands above assume an approved reachable database and a new local configuration. If `.env` already exists, review it privately without replacing it. Opening the Flask app initially needs the session and password settings. Sign in at `http://127.0.0.1:5000/login` on a private workstation and start with the dashboard and a read-only `GET /api/kpis`. A fresh empty schema shows no demand and unavailable fulfilment KPIs. Follow the [workflow guide](END_TO_END_WORKFLOWS.md) for write verification in a disposable instance.

## 3. Prepare a database

1. Verify the host, database and appropriate privileges with the database owner. Use the provider's verified CA for managed MySQL. Supply an administrative account to provision the schema and a separate application account for `SELECT`, `INSERT` and `UPDATE` on the approved application schema. Use a separate read-only account for evidence checks where practical.
2. On a new test or approved empty target, run [schema.sql](../sql/schema.sql) in Workbench. It creates and selects `butcherbridge_final`, and uses the server default storage engine. Ensure it is InnoDB before creation. When the provider supplies a differently named pre-created schema, request an administrator-reviewed bootstrap copy that selects only that approved schema and omits the database creation.
3. Optional for demonstrations only. Run [seed.sql](../sql/seed.sql) on an **empty disposable schema**. It selects `butcherbridge_final` and its upserts can overwrite fields on reused IDs. Confirm both scripts target the same isolated schema. Sample due dates are fixed and age out. The workflow verifier adds its own short-lived dated fixtures. Use approved input collection for a client dataset.
4. Check the engine and table names from the selected schema with read credentials.

```sql
SELECT DATABASE(), VERSION(), @@default_storage_engine;
SELECT TABLE_NAME, ENGINE
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
ORDER BY TABLE_NAME;
```

DDL does not include a migration ledger. Running the bootstrap against an existing installation will not transform earlier tables into the current shape. Treat any migration, seed on a shared instance, or data correction as a separate approved operation.

## 4. Configure secrets and environment

| Variable | Purpose and value |
|---|---|
| `DB_HOST`, `DB_PORT` | Approved hostname and port. Port defaults to 3306. For localhost disposable use, choose 127.0.0.1 and the instance port. |
| `DB_NAME` | Application schema. The default script uses `butcherbridge_final`. |
| `DB_USER`, `DB_PASSWORD` | Restricted application principal and secret. |
| `DB_SSL_CA` | Readable CA path for verified hosted TLS. Leave empty only for isolated local development. Flask verifies certificate and hostname when configured. |
| `APP_ENV` | `production` requires DB CA configuration and marks the session cookie Secure. Use HTTPS in that mode. `development` is for local verification. |
| `SECRET_KEY` | High-entropy, stable session signing secret for the deployment. Rotation invalidates existing sessions. |
| `APP_PASSWORD` | Private group demonstration password. Deliver through an approved private channel. |
| `GROUP_PLANNING_MAX_RETAILERS`, `GROUP_PLANNING_MAX_QUOTE_EVALUATIONS`, `GROUP_PLANNING_MAX_SEARCH_NODES` | Optional nonnegative integer solver bounds. Defaults 8, 5,000 and 100,000. Document and retest any override and keep the same settings on each worker. |

Copy [the example](../.env.example) and replace placeholders locally. Keep secrets in an ignored `.env` or managed secret store. On hosted deployments with secret injection, leave `.env` absent because the current loader gives local file values precedence. Check the working directory when resolving relative CA paths. Never include credentials, cookies, private keys or raw client data in videos, screenshots, logs or the submission archive.

## 5. Verify after installation

The two unittest suites run separately. The root invocation exercises the original classroom model. Use `-B` to avoid writing bytecode into the repository.

```powershell
# From the repository root
.\final_app\.venv\Scripts\python.exe -B -m unittest discover -v
Set-Location final_app
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -B demo_comparison.py
```

```bash
# From the repository root
./final_app/.venv/bin/python -B -m unittest discover -v
(cd final_app && ./.venv/bin/python -B -m unittest discover -s tests -v)
./final_app/.venv/bin/python -B final_app/demo_comparison.py
```

Run the [disposable browser and database verification](END_TO_END_WORKFLOWS.md#reproduce-in-a-disposable-instance) before handing over a release. Use the [API reference](API_DOCUMENTATION.md) to check a real session and read-only endpoint response on any authorised hosted instance. Registration of a host, rollout and live data authorisation are separate from a local test.

## Operating environment and limitations

- The local startup in `app.py` is a Flask development server with debug disabled. Use a supported WSGI server behind an HTTPS reverse proxy for an authorised private demonstration host. An operator may install Gunicorn on Linux or Waitress on Windows and target the WSGI callable `app:app` from `final_app/`. A hosting manifest, production WSGI dependency and hosted URL have yet to be supplied or verified.
- Configuration lives in environment variables read by `app.py` and `db.py`. Routes share a single Flask app. There is no `config.py`, app factory, Flask Blueprint or ORM model package. The separate DB, evaluation and solver modules currently carry those boundaries. Review a framework refactor only against a confirmed rubric or operating need.
- Shared password sessions are suited to a controlled demo. Per-user authorisation, CSRF protection, brute-force throttling, and durable event auditing would be needed before broader access. Store and rotate cookies and DB/password secrets under the operator's access policy.
- Scope the app to the supported lanes and data. Monitor request latency, query count, 5xx, transaction errors, connection limits, solver fallback frequency and backup age. The dashboard evaluates both plans from a short read-only snapshot. Standalone decisions use independent reads. Quoted costs and eligibility remain subject to the supplier's actual terms and current availability.

## Backup, restore and rollback

Use the provider's approved encrypted snapshot or a logical dump with an account allowed to read the relevant metadata. Before a planned change, record the backup ID, Git SHA, approximate restore window and operator responsible for recovery. Retain backups privately according to the agreed data policy. The following are command templates for an authorised operator. Prompt for passwords and use actual values from a private configuration.

```bash
mysqldump --host="$bb_backup_host" --user="$bb_backup_user" --password \
  --ssl-mode=VERIFY_IDENTITY --ssl-ca="$bb_ca" --single-transaction \
  --no-tablespaces --set-gtid-purged=OFF --skip-add-drop-table "$bb_database" > "$bb_private_dump"
```

**Run the restore command only against an empty disposable database.** Check the destination hostname and schema before importing, and review the dump for schema-selection statements or unexpected operations. Live or shared-database recovery requires separate approval and an operator-led recovery plan.

```bash
mysql --host="$bb_restore_test_host" --user="$bb_restore_test_user" --password \
  --ssl-mode=VERIFY_IDENTITY --ssl-ca="$bb_restore_ca" "$bb_empty_restore_schema" < "$bb_private_dump"
```

Provider permissions can restrict logical backup and restore. Use managed snapshots or consult the database owner when tooling is unavailable. The command shown covers tables and their data. Include any provider-specific metadata separately if it is in use. After the isolated restore, compare table engines, row counts, representative DECIMAL and FK records, and authenticated read endpoints. Record actual recovery time and confirm which writes fall outside the backup. This handover provides the procedure. A recovery drill on the intended deployment remains unverified.

For an app-only rollback, identify the last approved healthy SHA and restart that build from a separate release directory with the known good configuration. Compare schema compatibility first, then smoke-test sign-in, read routes and KPI rendering. Escalate schema or data recovery to the owner with a written plan and a fresh backup. Avoid classroom resets on shared deployments.

## Logs and troubleshooting

| Symptom | Checks |
|---|---|
| 401 on an API request | Establish a valid login session and send its cookie. Confirm the proxy is HTTPS for Secure cookies. |
| 405 on an API request | Check the documented method and the response's `Allow` header. |
| MySQL connectivity or TLS failure | Check `DB_HOST`, port, access rules, CA path and hostname. Confirm the application account has privileges on the selected schema. |
| Missing rows or closed window | Confirm the schema and dates, compare status/filter and verify the reference catalogs. Collect changes through the documented routes. |
| 409 conflict | Check reference IDs and unique offer/window or tier keys. Verify current state before retrying. |
| 500 or planner fallback | Read protected server logs for transaction/runtime causes and the UI for explicit planning-limit reasons. Set bounds and manage data volume in the authorised environment. |

Flask uses server-side logging and generic API errors for database integrity and unhandled exceptions. The process currently emits Python console logs. An operator should set log access, retention and rotation on the host, redact credentials or primary evidence from shared incident notes, and retain only approved backup and screen captures.
