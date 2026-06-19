# Data Engineer Tech Challenge

## Repository Structure

```
├── section3/
│   ├── design1/               ← Database access strategy (RBAC)
│   │   ├── README.md
│   │   ├── ddl.sql            ← PostgreSQL schema (Section 2 reference)
│   │   └── rbac.sql           ← Role & permission scripts
│   └── design2/               ← Cloud data infrastructure (AWS)
│       ├── README.md          ← Full architecture documentation
│       ├── architecture.md    ← Mermaid diagrams (3 views)
│       └── configs/
│           ├── s3-lifecycle.json
│           ├── iam-roles.json
│           └── lambda_processor.py
└── README.md                  ← This file
```

## Section 3 — System Design

### Design 1: Database Access Strategy
Role-based access control (RBAC) for a PostgreSQL e-commerce database shared across Logistics, Analytics, and Sales teams. Each team is granted only the permissions required for their function.

→ See [section3/design1/README.md](./section3/design1/README.md)

### Design 2: Cloud Data Infrastructure (AWS)
End-to-end AWS architecture for an image processing company. Covers dual ingestion (API upload + Kafka stream), serverless processing, 7-day compliant data purge, and a BI analytics layer.

→ See [section3/design2/README.md](./section3/design2/README.md)
