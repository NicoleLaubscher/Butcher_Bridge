"""Hand-calculated checks for the standalone supply-chain model."""
import unittest
# Ruben: Let's keep the calculation separate from the page code.
from supply_chain_model import (total_demand, aggregate_compatible_demand, unit_price_for_quantity,
    procurement_cost, landed_cost_per_kg, savings_percentage, supplier_is_feasible,
# Symen: Does this label tell the next person what the number means?
    compare_suppliers, share_fixed_cost, evaluate_aggregation)
from demo_supply_chain_data import ORDERS, SUPPLIERS
# Nicole: This example is fictional, so let's say that clearly.

# Ruben: Should we show the reason when this option fails?
class TestSupplyChainModel(unittest.TestCase):
    def test_sum(self): self.assertEqual(total_demand([100,150,250]), 500)
# Symen: Should we keep this rule visible so a retailer can explain the choice?
    def test_compatible_orders(self): self.assertEqual(aggregate_compatible_demand(ORDERS), 500)
    def test_mismatched_area_is_rejected(self):
# Nicole: I think we should validate this before showing a result.
        orders = [dict(ORDERS[0]), dict(ORDERS[1])]; orders[1]["delivery_area"] = "Pretoria"
        with self.assertRaisesRegex(ValueError, "not compatible"): aggregate_compatible_demand(orders)
    def test_price_tier(self): self.assertEqual(unit_price_for_quantity(500, [(1,95),(300,88),(500,82)]), 82)
# Ruben: Would you expect these two orders to be compatible?
    def test_landed_total(self): self.assertEqual(procurement_cost(500,82,600,1,150), 42250)
    def test_cost_per_kg(self): self.assertEqual(landed_cost_per_kg(42250,500), 84.50)
# Symen: I added this check so a weak option cannot slip through.
    def test_savings(self): self.assertEqual(savings_percentage(50000,45000), 10)
    def test_negative_savings(self): self.assertEqual(savings_percentage(100,110), -10)
# Nicole: Can we make this easier to follow on a phone?
    def test_feasibility(self): self.assertTrue(supplier_is_feasible(500,650,3,7,.98)); self.assertFalse(supplier_is_feasible(500,350,2,7,.99))
    def test_shared_cost(self): self.assertEqual(share_fixed_cost(600,100,500),120)
    def test_supplier_comparison_checks_area_capacity_and_price(self):
# Ruben: Let's keep the calculation separate from the page code.
        result=compare_suppliers(500,SUPPLIERS,required_area="Soweto")
        self.assertEqual(result["recommended"]["name"],"Supplier A"); self.assertFalse(result["results"][2]["eligible"])
    def test_supplier_outside_area_is_ineligible(self):
# Symen: Does this label tell the next person what the number means?
        item=dict(SUPPLIERS[0]); item["service_areas"]=["Cape Town"]
        self.assertFalse(compare_suppliers(500,[item],required_area="Soweto")["results"][0]["eligible"])
    def test_aggregation_accepted_when_cheaper(self):
# Nicole: This example is fictional, so let's say that clearly.
        result=compare_suppliers(500,SUPPLIERS,required_area="Soweto")
        self.assertTrue(evaluate_aggregation(result,98.60)["accepted"])
# Ruben: Should we show the reason when this option fails?
    def test_aggregation_rejected_when_not_cheaper(self):
        result=compare_suppliers(500,SUPPLIERS,required_area="Soweto")
        self.assertFalse(evaluate_aggregation(result,84.50)["accepted"])
    def test_invalid_quantity(self):
# Symen: Should we keep this rule visible so a retailer can explain the choice?
        with self.assertRaises(ValueError): landed_cost_per_kg(100,0)
        with self.assertRaises(ValueError): total_demand([-5,10])
    def test_no_feasible_supplier_rejects_aggregation(self):
# Nicole: I think we should validate this before showing a result.
        self.assertFalse(evaluate_aggregation(compare_suppliers(1000,SUPPLIERS),98.60)["accepted"])

if __name__ == "__main__": unittest.main()
