# Financial Report Analyzer — Complete AWS Pipeline

End-to-end system for ingesting annual/quarterly PDF reports and producing
structured financial analysis with supporting sentence evidence.

Accuracy 0.797 · Macro F1 0.737

---

## Architecture

```
PDF upload (Web API)
        │
        ▼
API Gateway → ingestion/Lambda → S3 raw bucket
                                        │
                                        ▼ (S3 trigger)
                               parsing/Lambda
                               └─ Textract (~3,000 sentences)
                               └─ S3 Parquet (processed bucket)
                               └─ OpenSearch bulk index
                                        │
                                        ▼ (Step Functions)
                    ┌───────────────────┴───────────────────┐
                    │   Per metric (parallel, MaxConcurrency=5)  │
                    │                                            │
                    │  stage1/Lambda                             │
                    │  └─ OpenSearch BM25 search                 │
                    │  └─ TF-IDF re-rank  →  100 candidates      │
                    │           │                                 │
                    │           ▼                                 │
                    │  stage2/Lambda → SageMaker Endpoint         │
                    │  └─ Keras BiLSTM classifier                │
                    │  └─ Top-3 sentences + confidence scores    │
                    └───────────────────┬───────────────────┘
                                        │
                                        ▼
                               assembly/Lambda
                               └─ report.md  (amazon_630.md format)
                               └─ result.json (amazon_630.json format)
                               └─ written to S3 processed bucket
```

---

## Directory structure

```
financial-report-analyzer/
│
├── ingestion/
│   └── lambda_handler.py        API Gateway → S3 raw bucket
│
├── parsing/
│   └── lambda_handler.py        Textract → S3 Parquet + OpenSearch
│
├── stage1_retrieval/
│   └── lambda_handler.py        OpenSearch BM25 + TF-IDF  →  100 candidates
│
├── stage2_classification/
│   ├── inference.py             SageMaker entry point (model_fn / predict_fn)
│   ├── lambda_handler.py        Calls SageMaker Endpoint, returns Top-3
│   ├── model/
│   │   └── save_model.py        Save + package trained Keras BiLSTM model
│   ├── deploy/
│   │   └── upload_and_deploy.py Upload to S3 + deploy SageMaker Endpoint
│   └── test/
│       └── test_local.py        Local model test (no AWS needed)
│
├── assembly/
│   └── lambda_handler.py        Merges Top-3 + field values → report.md + result.json
│
└── infra/
    ├── main.tf                  S3 buckets, IAM roles, Lambda functions, S3 trigger
    └── step_functions.tf        Step Functions state machine (Stage 1 → Stage 2 → Assembly)
```

---

## Step-by-step setup

### 1. Deploy model to SageMaker (do this first)

```bash
# Save and package your trained BiLSTM model
python stage2_classification/model/save_model.py

# Test locally (no AWS needed)
python stage2_classification/test/test_local.py

# Upload to S3 and deploy endpoint
pip install boto3 sagemaker
python stage2_classification/deploy/upload_and_deploy.py
```

### 2. Deploy infrastructure with Terraform

```bash
cd infra
terraform init

# Package all Lambda code first
cd ..
zip -r infra/lambda_functions.zip ingestion/ parsing/ stage1_retrieval/ \
    stage2_classification/lambda_handler.py assembly/ -x "*__pycache__*"

cd infra
terraform plan \
  -var="opensearch_host=your-domain.ap-southeast-1.es.amazonaws.com"

terraform apply \
  -var="opensearch_host=your-domain.ap-southeast-1.es.amazonaws.com"
```

### 3. Test the full pipeline

Upload a PDF via API Gateway:

```bash
curl -X POST \
  "https://your-api-id.execute-api.ap-southeast-1.amazonaws.com/prod/upload?company=amazon&year=2026&type=annual" \
  -H "Content-Type: application/pdf" \
  --data-binary @amazon_annual_report_2026.pdf
```

Check the output in S3:

```
s3://financial-report-analyzer-processed/reports/amazon/2026/{file_id}_report.md
s3://financial-report-analyzer-processed/reports/amazon/2026/{file_id}_result.json
```

### 4. Clean up (to avoid ongoing charges)

```bash
# Delete SageMaker endpoint (most expensive resource)
aws sagemaker delete-endpoint --endpoint-name bilstm-financial-classifier

# Destroy all Terraform-managed resources
cd infra
terraform destroy -var="opensearch_host=your-domain..."
```

---

## Key design decisions

| Decision | Why |
|---|---|
| Step Functions orchestrates Stage 1 → Stage 2 | Separates concerns; easy to retry individual stages |
| Map state with MaxConcurrency=5 | Runs all metrics in parallel; safe concurrency limit |
| OpenSearch BM25 first, then TF-IDF re-rank | BM25 is fast; TF-IDF refines the ranking cheaply in Lambda |
| SageMaker ml.m5.xlarge (CPU) | BiLSTM inference is fast enough on CPU; no GPU cost |
| Parquet + partitioned by company/year | Athena scans only the relevant partition per query |
