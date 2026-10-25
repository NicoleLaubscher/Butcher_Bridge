# ButcherBridge · BFB 321 Group 06

ButcherBridge is a course demonstration of how local butcheries could compare compatible group demand with supplier capacity, service and full delivered cost. It covers the Semester Project Guide's Steps 1 and 2: a responsive web interface and a standalone, documented supply-chain calculation model with hand-checked unit tests.

## Team

- Symen le Roux — u23608197
- Nicole Laubscher — u23530317
- Ruben Boonstra — u24588742

## Run the demonstration

1. Install Python 3.10 or newer.
2. From this folder, create and activate a virtual environment if desired.
3. Install dependencies with `python -m pip install -r requirements.txt`.
4. Start the site with `python run_butcherbridge_demo.py` and open `http://127.0.0.1:5000`.
5. Run standalone model checks with `python -m unittest -v`.

## Descriptive files

- `butcherbridge_demo_app.py` contains the Flask routes and display preparation.
- `supply_chain_model.py` contains the standard-library-only calculation logic.
<!-- Ruben: If we update the fictional values, should we check every number against the model's tests? -->
- `demo_supply_chain_data.py` contains fictional example retailers, suppliers and deliveries.
- `test_supply_chain_model.py` checks formulas and decisions against hand-calculated cases.
- `templates/` contains the shared page layout, dashboard, retailer/supplier form previews and methodology page.
- `static/butcherbridge_design.css` styles the responsive white-and-black interface; `static/nguni-background.jpg` is the Nguni background image.

## Step 1 interface coverage

The site has responsive dashboard, retailer-demand, supplier-offer and methodology pages; reusable shared navigation and layout; labelled form fields, required/range constraints, validation messages, keyboard focus indicators, skip navigation, table captions and mobile-friendly tables. The two input flows validate previews only. They do not save orders, publish offers, or maintain a database.

## Step 2 model coverage

The model checks matching product, specification, needed date and delivery area before aggregation; volume price tiers; total landed cost; delivered cost per kg; baseline savings; capacity, lead-time, fill-rate, service-area and price-tier feasibility; proportional fixed-cost allocation; and post-order fill, on-time, OTIF and cost variance. It rejects group buying when no supplier qualifies or when the group option is not cheaper than the individual baseline.

## Illustrative scenario and limitations

Three compatible sample orders (100, 150 and 250 kg) total 500 kg. Supplier A's sample 500 kg tier is R82/kg. Landed cost is `500 × 82 + 600 + 500 × 1 + 150 = R42,250`, or R84.50/kg. The individual baseline is R95/kg plus R600 delivery per retailer, giving `(500 × 95 + 3 × 600) / 500 = R98.60/kg`. These fictional numbers demonstrate the method; they are not measured savings or primary research. The project does not book orders, save user data, include authentication/API/database/deployment, or establish real price, service, quality or logistics data. The lecturer's feedback identifies primary-data validation and multiple realistic scenarios as later final-exam work, beyond this Step 1 and 2 submission.

## Scope

This submission targets only Steps 1 and 2. It does not claim to complete later integration, deployment or impact evaluation requirements.


