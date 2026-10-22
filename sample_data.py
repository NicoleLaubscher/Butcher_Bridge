"""Fictional classroom demonstration data (not a database)."""
ORDERS = [
    {"retailer": "Northside Butchery", "product": "Beef", "quantity_kg": 100},
    {"retailer": "Market Butchery", "product": "Beef", "quantity_kg": 150},
    {"retailer": "Family Meats", "product": "Beef", "quantity_kg": 250},
]
SUPPLIERS = [
    {"name": "Supplier A", "capacity_kg": 650, "lead_days": 3,
     "fill_rate": .98, "price_tiers": [(1, 95), (300, 88), (500, 82)],
     "delivery": 600, "variable_delivery": 1, "handling": 150},
    {"name": "Supplier B", "capacity_kg": 900, "lead_days": 4,
     "fill_rate": .97, "price_tiers": [(1, 93), (300, 86), (500, 84)],
     "delivery": 350, "variable_delivery": .5, "handling": 100},
    {"name": "Supplier C", "capacity_kg": 350, "lead_days": 2,
     "fill_rate": .99, "price_tiers": [(1, 89), (300, 80)],
     "delivery": 200, "variable_delivery": 0, "handling": 100},
]
