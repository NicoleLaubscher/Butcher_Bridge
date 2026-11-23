-- Execute in MySQL Workbench 8.0 CE on the SHARED hosted MySQL server.
-- Provider may supply a pre-created database. Select it first if CREATE DATABASE is restricted.

CREATE DATABASE IF NOT EXISTS butcherbridge_final
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;

USE butcherbridge_final;
CREATE TABLE IF NOT EXISTS retailers (
 id BIGINT PRIMARY KEY AUTO_INCREMENT,
 name VARCHAR(120) NOT NULL UNIQUE,
 area VARCHAR(100) NOT NULL,
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS products (
 id BIGINT PRIMARY KEY AUTO_INCREMENT,
 name VARCHAR(100) NOT NULL,
 specification VARCHAR(180) NOT NULL,
 UNIQUE KEY uq_product (name,specification),
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS order_windows (
 id BIGINT PRIMARY KEY AUTO_INCREMENT,
 label VARCHAR(100) NOT NULL UNIQUE,
 closes_at DATETIME NOT NULL,
 status ENUM('open','closed') NOT NULL DEFAULT 'open',
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS demand_orders (
 id BIGINT PRIMARY KEY AUTO_INCREMENT,
 retailer_id BIGINT NOT NULL,
 product_id BIGINT NOT NULL,
 window_id BIGINT NOT NULL,
 needed_date DATE NOT NULL,
 delivery_area VARCHAR(100) NOT NULL,
 quantity_kg DECIMAL(12,2) NOT NULL,
 baseline_price_per_kg DECIMAL(12,2) NOT NULL,
 baseline_logistics_cost DECIMAL(12,2) NOT NULL DEFAULT 0,
 baseline_trips INT NOT NULL DEFAULT 1,
 baseline_distance_km DECIMAL(12,2) NOT NULL DEFAULT 0,
 status ENUM('draft','committed','withdrawn','fulfilled') NOT NULL DEFAULT 'draft',
 evidence_type ENUM('primary','quoted','estimated','simulated') NOT NULL DEFAULT 'simulated',
 evidence_note VARCHAR(500) NULL,
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
 CONSTRAINT fk_demand_retailer FOREIGN KEY (retailer_id) REFERENCES retailers(id),
 CONSTRAINT fk_demand_product FOREIGN KEY (product_id) REFERENCES products(id),
 CONSTRAINT fk_demand_window FOREIGN KEY (window_id) REFERENCES order_windows(id),
 CONSTRAINT chk_demand_quantity CHECK (quantity_kg > 0),
 CONSTRAINT chk_demand_baseline CHECK (baseline_price_per_kg >= 0 AND baseline_logistics_cost >= 0 AND baseline_trips >= 0 AND baseline_distance_km >= 0),
 INDEX ix_demand_group (window_id,product_id,needed_date,delivery_area,status)
);
CREATE TABLE IF NOT EXISTS suppliers (
 id BIGINT PRIMARY KEY AUTO_INCREMENT,
 name VARCHAR(120) NOT NULL UNIQUE,
 service_area VARCHAR(100) NOT NULL,
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS supplier_offers (
 id BIGINT PRIMARY KEY AUTO_INCREMENT,
 supplier_id BIGINT NOT NULL,
 product_id BIGINT NOT NULL,
 capacity_kg DECIMAL(12,2) NOT NULL,
 lead_days INT NOT NULL,
 fill_rate DECIMAL(5,4) NOT NULL,
 fixed_delivery DECIMAL(12,2) NOT NULL DEFAULT 0,
 variable_delivery_per_kg DECIMAL(12,2) NOT NULL DEFAULT 0,
 handling_cost DECIMAL(12,2) NOT NULL DEFAULT 0,
 coordinated_trips INT NOT NULL DEFAULT 1,
 coordinated_distance_km DECIMAL(12,2) NOT NULL DEFAULT 0,
 active BOOLEAN NOT NULL DEFAULT TRUE,
 evidence_type ENUM('primary','quoted','estimated','simulated') NOT NULL DEFAULT 'simulated',
 evidence_note VARCHAR(500) NULL,
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
 CONSTRAINT fk_offer_supplier FOREIGN KEY (supplier_id) REFERENCES suppliers(id),
 CONSTRAINT fk_offer_product FOREIGN KEY (product_id) REFERENCES products(id),
 CONSTRAINT chk_offer_values CHECK (capacity_kg > 0 AND lead_days >= 0 AND fill_rate >= 0 AND fill_rate <= 1 AND fixed_delivery >= 0 AND variable_delivery_per_kg >= 0 AND handling_cost >= 0),
 INDEX ix_offer_product (product_id,active)
);
CREATE TABLE IF NOT EXISTS price_tiers (
 id BIGINT PRIMARY KEY AUTO_INCREMENT,
 offer_id BIGINT NOT NULL,
 min_quantity_kg DECIMAL(12,2) NOT NULL,
 price_per_kg DECIMAL(12,2) NOT NULL,
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
 CONSTRAINT fk_tier_offer FOREIGN KEY (offer_id) REFERENCES supplier_offers(id) ON DELETE CASCADE,
 CONSTRAINT chk_tier CHECK (min_quantity_kg > 0 AND price_per_kg >= 0),
 UNIQUE KEY uq_tier (offer_id,min_quantity_kg)
);
CREATE TABLE IF NOT EXISTS allocations (
 id BIGINT PRIMARY KEY AUTO_INCREMENT,
 offer_id BIGINT NOT NULL,
 window_id BIGINT NOT NULL,
 quantity_kg DECIMAL(12,2) NOT NULL,
 status ENUM('reserved','released') NOT NULL DEFAULT 'reserved',
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
 CONSTRAINT fk_alloc_offer FOREIGN KEY (offer_id) REFERENCES supplier_offers(id),
 CONSTRAINT fk_alloc_window FOREIGN KEY (window_id) REFERENCES order_windows(id),
 CONSTRAINT chk_alloc_positive CHECK (quantity_kg > 0),
 UNIQUE KEY uq_offer_window (offer_id,window_id)
);
CREATE TABLE IF NOT EXISTS fulfilments (
 id BIGINT PRIMARY KEY AUTO_INCREMENT,
 demand_order_id BIGINT NOT NULL UNIQUE,
 delivered_kg DECIMAL(12,2) NOT NULL,
 planned_days INT NOT NULL,
 actual_days INT NOT NULL,
 quoted_cost DECIMAL(12,2) NOT NULL,
 actual_cost DECIMAL(12,2) NOT NULL,
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
 CONSTRAINT fk_fulfilment_order FOREIGN KEY (demand_order_id) REFERENCES demand_orders(id),
 CONSTRAINT chk_fulfilment CHECK (delivered_kg >= 0 AND planned_days >= 0 AND actual_days >= 0 AND quoted_cost > 0 AND actual_cost >= 0)
);
