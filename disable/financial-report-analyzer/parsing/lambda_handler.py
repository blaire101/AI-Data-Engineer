"""
parsing/lambda_handler.py
--------------------------
Triggered by S3 ObjectCreated on the raw bucket.
Calls Amazon Textract to extract all sentences from the PDF,
then writes results to:
  - S3 processed bucket (Parquet, partitioned by company/year)
  - OpenSearch index (for Stage 1 keyword retrieval)
"""

import boto3
import json
import os
import io
from datetime import datetime, timezone
from urllib.parse import unquote_plus

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from opensearchpy import OpenSearch, helpers, AWSV4SignerAuth, RequestsHttpConnection

# ── AWS clients ──────────────────────────────────────────────────────────────
textract  = boto3.client("textract")
s3        = boto3.client("s3")

# ── Config from environment variables ────────────────────────────────────────
PROCESSED_BUCKET  = os.environ["PROCESSED_BUCKET"]
OPENSEARCH_HOST   = os.environ["OPENSEARCH_HOST"]
OPENSEARCH_INDEX  = os.environ.get("OPENSEARCH_INDEX", "annual-reports")


def get_opensearch_client():
    credentials = boto3.Session().get_credentials()
    auth = AWSV4SignerAuth(credentials, os.environ.get("AWS_REGION", "ap-southeast-1"))
    return OpenSearch(
        hosts=[{"host": OPENSEARCH_HOST, "port": 443}],
        http_auth=auth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
    )


def lambda_handler(event, context):
    record     = event["Records"][0]
    raw_bucket = record["s3"]["bucket"]["name"]
    s3_key     = unquote_plus(record["s3"]["object"]["key"])

    # Extract metadata from S3 key: raw/{company}/{year}/{type}/{file_id}.pdf
    parts    = s3_key.split("/")
    company  = parts[1] if len(parts) > 1 else "unknown"
    year     = parts[2] if len(parts) > 2 else "unknown"
    file_id  = parts[-1].replace(".pdf", "")

    print(f"Processing: s3://{raw_bucket}/{s3_key}")

    # ── Step 1: Textract — extract all sentences ──────────────────────────
    response  = textract.detect_document_text(
        Document={"S3Object": {"Bucket": raw_bucket, "Name": s3_key}}
    )

    sentences = []
    for i, block in enumerate(response["Blocks"]):
        if block["BlockType"] == "LINE" and block.get("Text", "").strip():
            sentences.append({
                "sentence_id": i,
                "file_id":     file_id,
                "company":     company,
                "year":        year,
                "page":        block.get("Page", 1),
                "text":        block["Text"].strip(),
                "word_count":  len(block["Text"].split()),
                "confidence":  round(block.get("Confidence", 0) / 100, 4),
                "extracted_at": datetime.now(timezone.utc).isoformat(),
            })

    print(f"Extracted {len(sentences)} sentences (target ~3,000)")

    # ── Step 2: Write to S3 as Parquet ────────────────────────────────────
    df     = pd.DataFrame(sentences)
    table  = pa.Table.from_pandas(df)
    buf    = io.BytesIO()
    pq.write_table(table, buf, compression="snappy")

    parquet_key = f"parsed/company={company}/year={year}/{file_id}.parquet"
    s3.put_object(
        Bucket=PROCESSED_BUCKET,
        Key=parquet_key,
        Body=buf.getvalue(),
    )
    print(f"Written Parquet: s3://{PROCESSED_BUCKET}/{parquet_key}")

    # ── Step 3: Bulk index to OpenSearch ─────────────────────────────────
    client  = get_opensearch_client()
    actions = [
        {
            "_index": OPENSEARCH_INDEX,
            "_id":    f"{file_id}_{s['sentence_id']}",
            "_source": s,
        }
        for s in sentences
    ]

    success, errors = helpers.bulk(client, actions, chunk_size=500)
    print(f"OpenSearch: indexed {success} docs, {len(errors)} errors")

    return {
        "statusCode":         200,
        "file_id":            file_id,
        "sentences_extracted": len(sentences),
        "parquet_key":        parquet_key,
    }
