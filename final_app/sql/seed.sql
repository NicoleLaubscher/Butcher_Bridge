-- FICTIONAL DEMONSTRATION ONLY. Not evidence of real supplier prices or actual benefits.
USE butcherbridge_final;
INSERT INTO retailers (id,name,area) VALUES (1,'Northside Butchery','Soweto'),(2,'Market Butchery','Soweto'),(3,'Family Meats','Soweto') ON DUPLICATE KEY UPDATE name=VALUES(name);
INSERT INTO products (id,name,specification) VALUES (1,'Beef','Chilled boneless beef') ON DUPLICATE KEY UPDATE name=VALUES(name);
INSERT INTO order_windows (id,label,closes_at,status) VALUES (1,'Demonstration - group 1','2027-12-01 18:00:00','open'),(2,'Demonstration - capacity conflict','2027-12-02 18:00:00','open') ON DUPLICATE KEY UPDATE label=VALUES(label);
INSERT INTO suppliers (id,name,service_area) VALUES (1,'Supplier A','Soweto'),(2,'Supplier B','Soweto'),(3,'Supplier C','Soweto') ON DUPLICATE KEY UPDATE name=VALUES(name);
INSERT INTO supplier_offers (id,supplier_id,product_id,capacity_kg,lead_days,fill_rate,fixed_delivery,variable_delivery_per_kg,handling_cost,coordinated_trips,coordinated_distance_km) VALUES
(1,1,1,650,3,0.9800,600,1,150,1,45),(2,2,1,900,4,0.9700,350,0.5,100,1,50),(3,3,1,350,2,0.9900,200,0,100,1,42)
ON DUPLICATE KEY UPDATE capacity_kg=VALUES(capacity_kg);
INSERT INTO price_tiers (offer_id,min_quantity_kg,price_per_kg) VALUES
(1,1,95),(1,300,88),(1,500,82),(2,1,93),(2,300,86),(2,500,84),(3,1,89),(3,300,80)
ON DUPLICATE KEY UPDATE price_per_kg=VALUES(price_per_kg);
INSERT INTO demand_orders (id,retailer_id,product_id,window_id,needed_date,delivery_area,quantity_kg,baseline_price_per_kg,baseline_logistics_cost,baseline_trips,baseline_distance_km,status,evidence_type,evidence_note) VALUES
(1,1,1,1,'2027-12-08','Soweto',100,95,600,1,25,'committed','simulated','Illustrative course scenario'),
(2,2,1,1,'2027-12-08','Soweto',150,95,600,1,30,'committed','simulated','Illustrative course scenario'),
(3,3,1,1,'2027-12-08','Soweto',250,95,600,1,40,'committed','simulated','Illustrative course scenario')
ON DUPLICATE KEY UPDATE quantity_kg=VALUES(quantity_kg);
