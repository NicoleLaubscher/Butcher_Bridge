# ButcherBridge - BFB 321 Group 06 Semester Project FrontEnd description

This smaller, original student-readable demonstration was reconstructed from the larger
ButcherBridge Flask/MySQL reference, focusing on the **Semester Project** row of the
*BFB 321 Supply Chain Web Application Project - End-to-End Development Guide*.

## Included for this stage
- Responsive web pages built with HTML and one CSS stylesheet
- Accessible navigation, form labels, validation hints and readable tables
- `calculations.py`: **standalone supply-chain model** (imports no Flask/database code)
- `test_calculations.py`: unit tests against known hand calculations
- `app.py`: optional lightweight Flask preview, using fictional sample data

## Folder structure
```
ButcherBridge_Semester_Project/
|-- app.py                   # simple website preview
|-- calculations.py          # supply chain formulas (standalone)
|-- sample_data.py           # fictional classroom data
|-- test_calculations.py     # tests independent of Flask
|-- requirements.txt
|-- templates/
|   |-- base.html
|   |-- index.html
|   `-- method.html
`-- static/
    `-- style.css
```

## Running on Windows
1. Open a terminal in this folder.
2. Run `py -m pip install -r requirements.txt`.
3. Start the example website with `py app.py`.
4. Visit `http://127.0.0.1:5000`.
5. Test independently with `py -m unittest -v`.

macOS / Linux: replace `py` with `python3`.

## How to explain the supply-chain concept
Three retailers order 100, 150 and 250 kg of the same beef product.
Combined demand = **500 kg**. Supplier A's price for that quantity is **R82/kg**.
Supplier A's total delivered cost is:
`500 * 82 + 600 + (500 * 1) + 150 = R42,250`, or **R84.50/kg**.
Supplier B costs `500 * 84 + 350 + (500 * 0.5) + 100 = R42,700`.
Supplier C cannot supply the required 500 kg (capacity is 350 kg).
Thus Supplier A is the lowest-cost eligible group supplier.

The classroom baseline is each retailer paying R95/kg plus R600 delivery.
Baseline = `500 * 95 + 3 * 600 = R49,300`.
Saving = `(49,300 - 42,250) / 49,300 * 100 = 14.30%` (rounded).
**These are illustrative assumptions, not measured real-world savings.**

## Model assumptions and limitations
- Only the same meat specification should be aggregated.
- Supplier rates represent quoted tier prices, in ZAR per kilogram.
- Supplier capacity, lead time and expected fill rate must pass feasibility checks.
- There is no database, login, REST API, actual order booking or saved state.
- No delivery area or on-time probability checks yet; those can be added in the final project.
- Tax, refrigeration losses, spoilage, vehicle routing and inventory carrying costs are excluded.
- The quantity form is a calculation demo and **does not** save orders.

## Scope boundary
The lecturer's **Final Project (Exam)** section includes API design, data model,
integration, deployment and impact/sustainability. Those features are intentionally
excluded from this Semester Project starting point.
