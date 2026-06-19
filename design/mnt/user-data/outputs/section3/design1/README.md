# Section 3 — Design 1: Database Access Strategy

## Overview

This design implements a **Role-Based Access Control (RBAC)** strategy for the e-commerce PostgreSQL database, ensuring each internal team has access only to what they need — following the **Principle of Least Privilege**.

---

## Database Schema (ERD)

```
members
  ├── membership_id (PK)
  ├── first_name, last_name
  ├── email, mobile
  ├── birthday, above_18
  └── created_at

items
  ├── item_id (PK, SERIAL)
  ├── item_name, manufacturer
  ├── cost, weight_kg
  ├── is_active          ← soft delete flag (used by Sales)
  └── created_at, updated_at

transactions
  ├── transaction_id (PK, SERIAL)
  ├── membership_id (FK → members)
  ├── total_price, total_weight_kg
  ├── status             ← updated by Logistics
  └── created_at, completed_at

transaction_items
  ├── id (PK, SERIAL)
  ├── transaction_id (FK → transactions)
  ├── item_id (FK → items)
  ├── quantity
  ├── unit_price         ← snapshot at time of purchase
  └── unit_weight_kg     ← snapshot at time of purchase
```

> `unit_price` and `unit_weight_kg` are stored as snapshots to preserve historical accuracy even if item details change later.

---

## Team Access Matrix

| Permission         | Logistics | Analytics | Sales |
|--------------------|-----------|-----------|-------|
| `members` SELECT   | ✅        | ✅        | ❌    |
| `items` SELECT     | ✅        | ✅        | ✅    |
| `items` INSERT     | ❌        | ❌        | ✅    |
| `items` UPDATE     | ❌        | ❌        | ✅ (limited columns) |
| `transactions` SELECT | ✅     | ✅        | ❌    |
| `transactions` UPDATE | ✅ (status/completed_at only) | ❌ | ❌ |
| `transaction_items` SELECT | ✅ | ✅       | ❌    |

---

## Team-by-Team Rationale

### Logistics
- **SELECT** on `transactions` and `transaction_items` to retrieve order weight and delivery details.
- **UPDATE** restricted to `status` and `completed_at` columns only — cannot modify pricing or member data.
- **SELECT** on `items` to retrieve weight per item if needed.

### Analytics
- **SELECT-only** across all relevant tables — no mutations permitted.
- `members` view (`analytics_members_view`) can be used to strip PII (email, mobile) depending on company data policy.

### Sales
- **INSERT** and **UPDATE** on `items` only — cannot access member or transaction data.
- Items are **soft-deleted** (`is_active = false`) rather than hard-deleted to preserve referential integrity in historical transactions.
- Cannot modify `item_id` or `created_at` (immutable columns excluded from UPDATE grant).

---

## Files

| File | Purpose |
|------|---------|
| `ddl.sql` | Full database schema with tables, constraints, and indexes |
| `rbac.sql` | Role creation, permission grants, user assignment |

## How to Apply

```bash
# 1. Spin up the database (see Section 2 Dockerfile)
docker-compose up -d

# 2. Apply schema
psql -U postgres -d ecommerce -f ddl.sql

# 3. Apply RBAC
psql -U postgres -d ecommerce -f rbac.sql
```
