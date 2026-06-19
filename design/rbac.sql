-- =============================================================
-- Section 3 Design 1: Role-Based Access Control (RBAC)
-- Teams: Logistics | Analytics | Sales
-- =============================================================

-- -------------------------------------------------------------
-- Step 1: Create roles
-- -------------------------------------------------------------
CREATE ROLE logistics_role;
CREATE ROLE analytics_role;
CREATE ROLE sales_role;

-- -------------------------------------------------------------
-- Step 2: Grant permissions per team
-- -------------------------------------------------------------

-- LOGISTICS
-- Needs: read sales details (especially weight), update transaction status
GRANT SELECT ON transactions         TO logistics_role;
GRANT SELECT ON transaction_items    TO logistics_role;
GRANT SELECT ON items                TO logistics_role;   -- to read item weight
GRANT SELECT ON members              TO logistics_role;   -- to read member info for delivery
GRANT UPDATE (status, completed_at)
           ON transactions           TO logistics_role;   -- only allowed to mark as completed

-- ANALYTICS
-- Needs: read-only access to all tables for reporting & analysis
GRANT SELECT ON members              TO analytics_role;
GRANT SELECT ON items                TO analytics_role;
GRANT SELECT ON transactions         TO analytics_role;
GRANT SELECT ON transaction_items    TO analytics_role;
-- Explicitly NO INSERT / UPDATE / DELETE

-- SALES
-- Needs: insert new items, soft-delete old items (set is_active = false)
-- Should NOT touch members or transactions
GRANT SELECT, INSERT ON items        TO sales_role;
GRANT UPDATE (is_active, item_name, manufacturer, cost, weight_kg, updated_at)
           ON items                  TO sales_role;
GRANT USAGE, SELECT ON SEQUENCE items_item_id_seq TO sales_role;  -- needed for SERIAL inserts

-- -------------------------------------------------------------
-- Step 3: Create application users and assign roles
-- (In production these would be service accounts / IAM-mapped roles)
-- -------------------------------------------------------------
CREATE USER logistics_user  WITH PASSWORD 'changeme_logistics';
CREATE USER analytics_user  WITH PASSWORD 'changeme_analytics';
CREATE USER sales_user      WITH PASSWORD 'changeme_sales';

GRANT logistics_role  TO logistics_user;
GRANT analytics_role  TO analytics_user;
GRANT sales_role      TO sales_user;

-- -------------------------------------------------------------
-- Step 4: Revoke default public schema privileges
-- (Principle of Least Privilege — deny all by default)
-- -------------------------------------------------------------
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO logistics_role, analytics_role, sales_role;

-- -------------------------------------------------------------
-- Step 5: Row-Level Security (optional but recommended)
-- Example: Analytics role cannot see member PII columns directly
-- Achieved via a view rather than RLS for simplicity
-- -------------------------------------------------------------
CREATE VIEW analytics_members_view AS
    SELECT membership_id, above_18, created_at   -- PII (email, mobile) excluded
    FROM members;

GRANT SELECT ON analytics_members_view TO analytics_role;
REVOKE SELECT ON members FROM analytics_role;          -- revoke direct table access
GRANT SELECT ON members TO analytics_role;             -- re-grant if full access is acceptable
-- NOTE: toggle above two lines based on company's PII policy

-- =============================================================
-- Summary of permissions
-- =============================================================
-- Role          | members | items            | transactions        | transaction_items
-- --------------|---------|------------------|---------------------|------------------
-- logistics     | SELECT  | SELECT           | SELECT, UPDATE(*)   | SELECT
-- analytics     | SELECT  | SELECT           | SELECT              | SELECT
-- sales         | -       | SELECT,INSERT,   | -                   | -
--               |         | UPDATE(*)        |                     |
-- =============================================================
