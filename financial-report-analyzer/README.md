# Financial Report Analyzer — AWS Pipeline

End-to-end system for ingesting annual and quarterly PDF reports and producing
structured financial analysis reports with supporting sentence evidence.

**Clients:** DBS · Credit Suisse · BCA  
**Model performance:** Accuracy 0.797 · Macro F1 0.737

---

## Architecture

![Architecture](./docs/architecture.svg)

**Three S3 buckets:**
- `S3 raw` — original PDFs
- `S3 processed` — parsed text and intermediate results
- `S3 models` — trained Keras model (tar.gz) loaded by SageMaker

**Pipeline flow:**  
PDF upload → API Gateway → ingestion Lambda → S3 raw  
→ Textract parsing Lambda → all text indexed into OpenSearch (~3,000 sentences)  
→ Step Functions (per metric, parallel):  
&nbsp;&nbsp;Stage 1: OpenSearch keyword retrieval → 100 candidates  
&nbsp;&nbsp;Stage 2: Keras endpoint on SageMaker → Top-3 + confidence scores  
→ Assembly Lambda → result.json → report.html → S3 analytics bucket

---

## Directory structure

```
financial-report-analyzer/
│
├── ingestion/
│   └── lambda_handler.py        API Gateway → S3 raw bucket
│
├── parsing/
│   └── lambda_handler.py        Textract → OpenSearch (all text indexed)
│
├── stage1_retrieval/
│   └── lambda_handler.py        OpenSearch keyword search → 100 candidates
│
├── stage2_classification/
│   ├── inference.py             SageMaker entry point (model_fn / predict_fn)
│   ├── lambda_handler.py        Calls SageMaker endpoint, returns Top-3
│   ├── model/
│   │   └── save_model.py        Save + package trained Keras model
│   ├── deploy/
│   │   └── upload_and_deploy.py Upload model to S3 + deploy SageMaker endpoint
│   └── test/
│       └── test_local.py        Local model test (no AWS needed)
│
├── assembly/
│   └── lambda_handler.py        Merges Top-3 + field values → result.json → report.html
│
├── docs/
│   └── architecture.svg         Architecture diagram
│
└── infra/
    ├── main.tf                  S3 buckets, IAM roles, Lambda functions, S3 trigger
    └── step_functions.tf        Step Functions state machine (Stage 1 → Stage 2 → Assembly)
```

---

## Step-by-step setup

### 1. Deploy model to SageMaker (do this first)

```bash
# Save and package your trained Keras model
python stage2_classification/model/save_model.py

# Test locally — no AWS account needed
python stage2_classification/test/test_local.py

# Upload model to S3 models bucket and deploy endpoint
pip install boto3 sagemaker
python stage2_classification/deploy/upload_and_deploy.py
```

### 2. Deploy infrastructure with Terraform

```bash
# Package all Lambda functions
zip -r infra/lambda_functions.zip ingestion/ parsing/ stage1_retrieval/ \
    stage2_classification/lambda_handler.py assembly/ -x "*__pycache__*"

cd infra
terraform init
terraform apply -var="opensearch_host=your-domain.ap-southeast-1.es.amazonaws.com"
```

### 3. Test the pipeline

Upload a PDF:

```bash
curl -X POST \
  "https://your-api-id.execute-api.ap-southeast-1.amazonaws.com/prod/upload?company=amazon&year=2026&type=annual" \
  -H "Content-Type: application/pdf" \
  --data-binary @amazon_annual_report_2026.pdf
```

Check output in S3 analytics bucket:

```
s3://financial-report-analyzer-analytics/reports/amazon/2026/{file_id}_report.html
s3://financial-report-analyzer-analytics/reports/amazon/2026/{file_id}_result.json
```

### 4. Clean up

```bash
# Delete SageMaker endpoint (most expensive running resource)
aws sagemaker delete-endpoint --endpoint-name keras-financial-classifier

# Destroy all Terraform resources
cd infra && terraform destroy -var="opensearch_host=your-domain..."
```

---

## Key design decisions

| Decision | Why |
|---|---|
| Step Functions orchestrates Stage 1 → Stage 2 | Separates concerns; per-metric retry without restarting the full pipeline |
| Map state with MaxConcurrency=5 | Runs all metrics in parallel; prevents Lambda throttling |
| OpenSearch for full-text indexing | All ~3,000 sentences indexed at parse time; keyword search at query time is instant |
| SageMaker ml.m5.xlarge (CPU) | Keras inference is fast enough on CPU; no GPU cost |
| Three separate S3 buckets | Clear separation of raw data, intermediate results, and final reports |
| result.json → report.html | Structured JSON enables programmatic access; HTML enables direct analyst access |
