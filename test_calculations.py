"""Unit tests with manually calculated answers; run: python -m unittest -v."""
import unittest
from calculations import (total_demand, unit_price_for_quantity,
    procurement_cost, landed_cost_per_kg, savings_percentage,
    supplier_is_feasible, compare_suppliers, share_fixed_cost)
from sample_data import SUPPLIERS

class TestButcherBridgeModel(unittest.TestCase):
    def test_aggregate_demand(self):
        # 100 + 150 + 250 = 500 kg
        self.assertEqual(total_demand([100,150,250]), 500)

    def test_bulk_price_tier(self):
        # 500 kg meets the 500-kg tier, priced at R82/kg
        self.assertEqual(unit_price_for_quantity(500, [(1,95),(300,88),(500,82)]),82)

    def test_total_landed_cost(self):
        # 500*82 + 600 + 500*1 + 150 = R42,250
        self.assertEqual(procurement_cost(500,82,600,1,150),42250)

    def test_cost_per_kg(self):
        # R42,250 / 500 = R84.50 per kg
        self.assertEqual(landed_cost_per_kg(42250,500),84.50)

    def test_savings(self):
        # (50000 - 45000)/50000*100 = 10%
        self.assertEqual(savings_percentage(50000,45000),10)

    def test_negative_savings_means_higher_cost(self):
        self.assertEqual(savings_percentage(100,110),-10)

    def test_supplier_feasibility(self):
        self.assertTrue(supplier_is_feasible(500,650,3,7,.98))
        self.assertFalse(supplier_is_feasible(500,350,2,7,.99))

    def test_shared_delivery(self):
        # Retailer ordered 100 of 500 kg; receives 20% of R600 fee
        self.assertEqual(share_fixed_cost(600,100,500),120)

    def test_recommendation_checks_capacity(self):
        result=compare_suppliers(500,SUPPLIERS)
        self.assertEqual(result['recommended']['name'],'Supplier A')
        self.assertFalse(result['results'][2]['eligible'])

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            landed_cost_per_kg(100,0)
        with self.assertRaises(ValueError):
            total_demand([-5,10])

if __name__ == '__main__':
    unittest.main()
