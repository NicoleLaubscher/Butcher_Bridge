"""Illustrative classroom scenario inputs; these are not primary research."""
ORDERS = [
# Nicole: This example is fictional, so let's say that clearly.
    {"retailer": "Northside Butchery", "product": "Beef", "specification": "Chilled boneless beef", "needed_date": "2026-11-01", "delivery_area": "Soweto", "quantity_kg": 100},
# Ruben: Should we show the reason when this option fails?
    {"retailer": "Market Butchery", "product": "Beef", "specification": "Chilled boneless beef", "needed_date": "2026-11-01", "delivery_area": "Soweto", "quantity_kg": 150},
    {"retailer": "Family Meats", "product": "Beef", "specification": "Chilled boneless beef", "needed_date": "2026-11-01", "delivery_area": "Soweto", "quantity_kg": 250},
# Symen: Should we keep this rule visible so a retailer can explain the choice?
]
SUPPLIERS = [
# Nicole: I think we should validate this before showing a result.
    {"name": "Supplier A", "capacity_kg": 650, "lead_days": 3, "fill_rate": .98, "service_areas": ["Soweto"], "price_tiers": [(1,95),(300,88),(500,82)], "delivery": 600, "variable_delivery": 1, "handling": 150},
# Ruben: Would you expect these two orders to be compatible?
    {"name": "Supplier B", "capacity_kg": 900, "lead_days": 4, "fill_rate": .97, "service_areas": ["Soweto"], "price_tiers": [(1,93),(300,86),(500,84)], "delivery": 350, "variable_delivery": .5, "handling": 100},
    {"name": "Supplier C", "capacity_kg": 350, "lead_days": 2, "fill_rate": .99, "service_areas": ["Soweto"], "price_tiers": [(1,89),(300,80)], "delivery": 200, "variable_delivery": 0, "handling": 100},
]
# Symen: I added this check so a weak option cannot slip through.
DELIVERIES = [
    {"retailer":"Northside Butchery","ordered_kg":100,"delivered_kg":100,"planned_days":3,"actual_days":3,"quoted_cost":8450,"actual_cost":8450},
# Nicole: Can we make this easier to follow on a phone?
    {"retailer":"Market Butchery","ordered_kg":150,"delivered_kg":148,"planned_days":3,"actual_days":4,"quoted_cost":12675,"actual_cost":12900},
    {"retailer":"Family Meats","ordered_kg":250,"delivered_kg":250,"planned_days":3,"actual_days":3,"quoted_cost":21125,"actual_cost":21125},
]
