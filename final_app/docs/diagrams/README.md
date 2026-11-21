# Submission diagrams and figure sources

| Figure | Editable source | Rendered output | What it shows |
|---|---|---|---|
| Database ERD | [database_erd.mmd](database_erd.mmd) | [database_erd.svg](database_erd.svg) | All nine physical tables and every declared FK |
| System architecture | [architecture.mmd](architecture.mmd) | [architecture.svg](architecture.svg) | Browser, Flask, MySQL, read/write boundaries and planning |
| Decision workflow | [decision_workflow.mmd](decision_workflow.mmd) | [decision_workflow.svg](decision_workflow.svg) | Demand, supplier evaluation, proposals and actual outcomes |
| Simulated cost comparison | [generate_impact_chart.py](../../scripts/generate_impact_chart.py) | [simulated_plan_costs.svg](simulated_plan_costs.svg) | Before and after plan costs calculated from production fixtures |

## Physical model details

The ERD follows [schema.sql](../../sql/schema.sql). Every table has an auto-increment BIGINT primary key. Dotted edges denote non-identifying relationships. Every child FK is required. Each order has zero or one fulfilment because the order FK there is unique. Each offer/window can have at most one allocation across both statuses. Each tier belongs to one offer and is deleted with it. The other FKs use MySQL's default restrictive delete behavior. Plan groups, quotes, and retailer cost shares are computed in memory.

| Table | Declared unique and secondary indexes beyond PK |
|---|---|
| `retailers` | UNIQUE `name` |
| `products` | `uq_product (name, specification)` |
| `order_windows` | UNIQUE `label` |
| `demand_orders` | `ix_demand_group (window_id, product_id, needed_date, delivery_area, status)` |
| `suppliers` | UNIQUE `name` |
| `supplier_offers` | `ix_offer_product (product_id, active)` |
| `price_tiers` | `uq_tier (offer_id, min_quantity_kg)` |
| `allocations` | `uq_offer_window (offer_id, window_id)` |
| `fulfilments` | UNIQUE `demand_order_id` |

MySQL adds FK supporting indexes where no existing index begins with the referencing column. Compare `SHOW INDEX` on the selected instance with the declared indexes and document any operational additions. The schema's timestamp pairs are on all tables except `price_tiers`. The audit fields are timestamps. The app does not maintain a per-user event history. CHECK constraints cover positive quantities/capacity and permitted numeric ranges in the DDL.

## Render and edit

The Mermaid files can be edited as text, imported as Mermaid source in diagrams.net, or rendered with Mermaid CLI. Run these commands from `final_app/docs/diagrams/`.

```bash
npx --yes --package @mermaid-js/mermaid-cli mmdc -c mermaid-config.json -i database_erd.mmd -o database_erd.svg
npx --yes --package @mermaid-js/mermaid-cli mmdc -c mermaid-config.json -i architecture.mmd -o architecture.svg
npx --yes --package @mermaid-js/mermaid-cli mmdc -c mermaid-config.json -i decision_workflow.mmd -o decision_workflow.svg
```

The CLI uses Chromium. Choose a local browser with its documented Puppeteer config if the default download is unavailable. These are documentation tools installed separately from Flask. The SVGs are suitable for scaling in an appendix. Use a landscape page or zoomed subsections if the full ERD labels do not fit.

Run the chart generator from the repository root in a Python environment with Matplotlib.

```bash
python -m pip install matplotlib
python -B final_app/scripts/generate_impact_chart.py
```
