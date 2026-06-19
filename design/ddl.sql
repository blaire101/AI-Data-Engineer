-- =============================================================
-- Section 2 & 3 Design 1: E-Commerce Database DDL
-- Database: PostgreSQL
-- =============================================================

-- -------------------------------------------------------------
-- Members table (sourced from successful membership applications)
-- -------------------------------------------------------------
CREATE TABLE members (
    membership_id   VARCHAR(100)    PRIMARY KEY,          -- e.g. Lam_a3f9b
    first_name      VARCHAR(100)    NOT NULL,
    last_name       VARCHAR(100)    NOT NULL,
    email           VARCHAR(255)    NOT NULL UNIQUE,
    mobile          VARCHAR(8)      NOT NULL,
    birthday        CHAR(8)         NOT NULL,             -- YYYYMMDD
    above_18        BOOLEAN         NOT NULL,
    created_at      TIMESTAMP       DEFAULT NOW()
);

-- -------------------------------------------------------------
-- Items table (products listed on the platform)
-- -------------------------------------------------------------
CREATE TABLE items (
    item_id         SERIAL          PRIMARY KEY,
    item_name       VARCHAR(255)    NOT NULL,
    manufacturer    VARCHAR(255)    NOT NULL,
    cost            NUMERIC(10, 2)  NOT NULL CHECK (cost >= 0),
    weight_kg       NUMERIC(8, 3)   NOT NULL CHECK (weight_kg >= 0),
    is_active       BOOLEAN         DEFAULT TRUE,         -- soft delete for Sales team
    created_at      TIMESTAMP       DEFAULT NOW(),
    updated_at      TIMESTAMP       DEFAULT NOW()
);

-- -------------------------------------------------------------
-- Transactions table (each purchase made by a member)
-- -------------------------------------------------------------
CREATE TABLE transactions (
    transaction_id      SERIAL          PRIMARY KEY,
    membership_id       VARCHAR(100)    NOT NULL REFERENCES members(membership_id),
    total_price         NUMERIC(10, 2)  NOT NULL CHECK (total_price >= 0),
    total_weight_kg     NUMERIC(10, 3)  NOT NULL CHECK (total_weight_kg >= 0),
    status              VARCHAR(50)     DEFAULT 'pending', -- pending | completed | cancelled
    created_at          TIMESTAMP       DEFAULT NOW(),
    completed_at        TIMESTAMP
);

-- -------------------------------------------------------------
-- Transaction line items (many-to-many: transaction <-> item)
-- -------------------------------------------------------------
CREATE TABLE transaction_items (
    id              SERIAL          PRIMARY KEY,
    transaction_id  INT             NOT NULL REFERENCES transactions(transaction_id),
    item_id         INT             NOT NULL REFERENCES items(item_id),
    quantity        INT             NOT NULL CHECK (quantity > 0),
    unit_price      NUMERIC(10, 2)  NOT NULL,             -- snapshot price at time of purchase
    unit_weight_kg  NUMERIC(8, 3)   NOT NULL              -- snapshot weight at time of purchase
);

-- -------------------------------------------------------------
-- Indexes for common query patterns
-- -------------------------------------------------------------
CREATE INDEX idx_transactions_membership  ON transactions(membership_id);
CREATE INDEX idx_transactions_status      ON transactions(status);
CREATE INDEX idx_transaction_items_txn    ON transaction_items(transaction_id);
CREATE INDEX idx_transaction_items_item   ON transaction_items(item_id);

-- -------------------------------------------------------------
-- Analyst sample queries
-- -------------------------------------------------------------

-- Q1: Top 10 members by total spending
-- SELECT m.membership_id, m.first_name, m.last_name,
--        SUM(t.total_price) AS total_spent
-- FROM transactions t
-- JOIN members m ON t.membership_id = m.membership_id
-- WHERE t.status = 'completed'
-- GROUP BY m.membership_id, m.first_name, m.last_name
-- ORDER BY total_spent DESC
-- LIMIT 10;

-- Q2: Top 3 most frequently purchased items
-- SELECT i.item_id, i.item_name,
--        SUM(ti.quantity) AS total_quantity_sold
-- FROM transaction_items ti
-- JOIN items i ON ti.item_id = i.item_id
-- JOIN transactions t ON ti.transaction_id = t.transaction_id
-- WHERE t.status = 'completed'
-- GROUP BY i.item_id, i.item_name
-- ORDER BY total_quantity_sold DESC
-- LIMIT 3;
