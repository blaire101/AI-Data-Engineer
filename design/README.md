# Section 3 — Design 2: Cloud Data Infrastructure (AWS)

## Overview

This document describes the end-to-end AWS architecture for a company whose core business is **image processing**. The system supports two ingestion paths — a REST API upload and a Kafka stream — processes images using the company's existing code, stores all data with a strict 7-day retention policy for compliance, and provides a managed Business Intelligence layer for analysts.

---

## Assumptions

1. Primary AWS region: **ap-southeast-1 (Singapore)**.
2. The company's image processing code is assumed to be packaged as a deployable unit (e.g. a Python module), hosted on Lambda as a Layer or container image.
3. The Kafka stream is sourced externally over the public internet using TLS. The EKS cluster running Kafka brokers is **company-managed** as explicitly required — not a fully managed MSK serverless service.
4. Analysts access BI tools via a browser dashboard — no direct AWS console or database access is granted.
5. The 7-day purge requirement applies to both raw images, processed outputs, and their associated metadata.

---

## Architecture Diagrams

Three formats are provided — use whichever works best for your submission:

| File | Format | Best for |
|------|--------|----------|
| `architecture.md` | Mermaid (2 diagrams) | GitHub rendering — renders directly in README |
| `architecture.svg` | SVG | Embedding in documents, draw.io-style visual |
| `architecture.drawio` | draw.io XML | Import into draw.io / diagrams.net for editing |

The Mermaid diagrams in `architecture.md` render automatically on GitHub without any tooling — recommended as the primary view.

---

## Components

### Ingestion Layer — Dual Path

The system accepts images from two distinct sources:

**Path 1 — Web App (REST API)**
Users upload images through a web application. Requests pass through **CloudFront**, which handles TLS termination at the edge and is backed by **AWS WAF** for DDoS protection and request filtering. **API Gateway** then validates authentication (via API Key or Amazon Cognito) and writes the image directly to S3 using an IAM role scoped to `PutObject` on the raw bucket only.

**Path 2 — Kafka Stream**
An external Kafka stream sends images over TLS to a **Network Load Balancer**, which routes into a self-managed **EKS cluster** running Kafka brokers. **MSK Connect** with an S3 Sink Connector reads from the Kafka topic and writes images into the same raw S3 bucket. Engineers manage the Kafka deployment via Kubernetes — configuration is versioned as Helm charts and ConfigMaps.

---

### Storage Layer

| Bucket | Encryption | Lifecycle |
|--------|-----------|-----------|
| S3 Raw Bucket | SSE-KMS (Customer Managed Key) | Hard delete after 7 days |
| S3 Processed Bucket | SSE-AES256 | Hard delete after 7 days |

Both buckets have Block All Public Access enabled. Versioning is disabled so that lifecycle deletion is clean and complete — retained versions would leave data beyond the 7-day compliance window.

---

### Processing Layer

**AWS Lambda** is triggered by S3 Event Notifications each time a new image lands in the raw bucket. Each image triggers a separate Lambda invocation, providing natural parallelism with no manual scaling configuration.

Lambda runs inside the **VPC in a private subnet** — it has no internet access and communicates with S3 and DynamoDB exclusively via **VPC Endpoints**, keeping all traffic within the AWS network. The company's processing code is deployed as a Lambda Layer.

After processing, Lambda writes:
- The processed image to the S3 Processed Bucket
- Image metadata (dimensions, file size, timestamps) plus a TTL timestamp to DynamoDB

---

### Metadata Layer

**Amazon DynamoDB** stores metadata for each image. A `ttl` attribute is set to 7 days from upload time. DynamoDB's native TTL feature automatically expires and deletes items after this period — no application code or scheduled job is required to enforce purge compliance.

---

### Business Intelligence Layer

```
S3 Processed Bucket
       ↓
  AWS Glue Crawler  (scheduled, detects schema automatically)
       ↓
  AWS Glue Data Catalog
       ↓
  Amazon Athena  (SQL queries directly on S3)
       ↓
  Amazon QuickSight  (BI dashboards for analysts)
```

Analysts authenticate via **IAM Identity Center (SSO)** — they access QuickSight dashboards through a browser, with no AWS console or direct data access. Their IAM role is scoped to read-only Athena query access and S3 read on the processed bucket only.

**Athena** is serverless and pay-per-query, with no infrastructure to maintain. Using **columnar file formats (Parquet)** and partition pruning keeps query costs low as data volume grows.

---

## Stakeholder Concerns

### Securing Access as the Company Expands

**IAM Identity Center (SSO)** centralises all human access. New team members are assigned permission sets rather than individual IAM users, making onboarding and offboarding auditable and consistent.

Every AWS service runs under its own **IAM Role** with the minimum permissions required for its function — no role can perform actions beyond its defined scope. As the company grows, **AWS Organizations with Service Control Policies (SCPs)** can enforce guardrails across multiple accounts (dev / staging / prod), preventing privilege escalation at the organisation level.

The EKS cluster runs in a **private subnet** with no public IP assignment. Access for engineers is managed through **AWS Systems Manager Session Manager** — no SSH bastion host is required, and all session activity is logged.

---

### Security of Data at Rest and in Transit

**At rest:**
- Raw images are encrypted with **SSE-KMS using a Customer Managed Key (CMK)**. Key rotation is enforced annually, and key usage is logged in CloudTrail.
- Processed images use **SSE-AES256** (AWS managed key).
- DynamoDB metadata is encrypted at rest using **AWS-managed KMS**.
- An S3 bucket policy enforces that any request not using `aws:SecureTransport` (i.e. not HTTPS) is denied.

**In transit:**
- All external traffic uses **HTTPS/TLS 1.2+**, enforced at CloudFront and API Gateway.
- Kafka producers connect over **TLS** — the NLB is configured to reject plaintext connections.
- Internal AWS service-to-service communication uses **VPC Endpoints** — traffic between Lambda, S3, and DynamoDB never traverses the public internet.
- Kafka credentials (bootstrap broker addresses, SASL credentials) are stored in **AWS Secrets Manager** and injected into EKS pods at runtime — never hardcoded in container images.

---

### Scaling to Meet User Demand While Keeping Costs Low

| Component | Scaling Mechanism | Cost Control |
|-----------|-----------------|-------------|
| CloudFront | Global edge, auto-scales | Cache hits reduce origin load |
| API Gateway | Managed, scales automatically | Pay-per-request, no idle cost |
| Lambda | Scales per invocation, no config required | Concurrency limit cap prevents cost spikes |
| EKS (Kafka) | Cluster Autoscaler adds/removes nodes | Spot Instances for worker nodes (60–70% savings) |
| DynamoDB | On-demand capacity mode | Pay per read/write, scales to zero |
| Athena | Serverless, scales per query | Parquet format + partitions reduce data scanned |
| QuickSight | SPICE in-memory cache | Pre-computed datasets reduce Athena query frequency |

---

### Maintenance of Environment and Assets

**Processing code:** Engineers deploy Lambda updates via a CI/CD pipeline (e.g. GitHub Actions → ECR → `update-function-code`). **Lambda aliases with weighted routing** enable canary deployments — 10% of traffic routes to the new version before a full rollout, limiting blast radius.

**Kafka on EKS:** The Kafka deployment is version-controlled as **Helm charts**. EKS managed node group rolling updates handle Kubernetes version upgrades with no manual intervention.

**Infrastructure as Code:** All AWS resources are defined in Terraform or AWS CDK — the entire environment is reproducible, auditable, and version-controlled. No manual console configuration.

**Monitoring:** **CloudWatch** collects Lambda metrics (error rate, duration, throttles), EKS pod logs, and S3 access logs. CloudWatch Alarms trigger SNS notifications to on-call channels for anomalies. **AWS X-Ray** traces requests end-to-end from API Gateway through Lambda for performance debugging.

---

## Cloud Best Practices Summary

| Principle | How it is addressed |
|-----------|-------------------|
| Manageability | CloudWatch + X-Ray observability; IaC for reproducibility; CI/CD for deployments |
| Scalability | Lambda auto-scales per event; EKS Cluster Autoscaler; DynamoDB on-demand; API Gateway managed |
| Secure | WAF, VPC private subnets, SSO, KMS CMK, IAM least-privilege per service, TLS everywhere |
| High Availability | Multi-AZ deployment across 3 AZs in ap-southeast-1 for Lambda, DynamoDB, EKS |
| Elastic | Lambda and DynamoDB scale to zero when idle; Spot Instances for batch workloads |
| Fault Tolerant / DR | S3 eleven-nines durability; DynamoDB point-in-time recovery; EKS multi-AZ node groups |
| Efficient | Serverless where possible; Parquet columnar format for Athena; SPICE caching in QuickSight |
| Low Latency | CloudFront edge caching; Lambda co-located with S3 in same region |
| Least Privilege | Every service role has only the exact actions required — no wildcard resources |

---

## File Structure

```
section3/design2/
├── README.md            ← This document (full stakeholder documentation)
├── architecture.md      ← Mermaid diagrams (high-level + data flow detail)
├── architecture.svg     ← SVG diagram (embed in docs or view directly)
└── architecture.drawio  ← draw.io XML (import into diagrams.net for editing)
```
