"""
ingestion/lambda_handler.py
---------------------------
Triggered by API Gateway when a user uploads an annual/quarterly report PDF.
Validates the file and stores it in the S3 raw bucket.
Downstream: S3 ObjectCreated event triggers parsing/lambda_handler.py.
"""

import boto3
import base64
import json
import os
import uuid
from datetime import datetime

s3 = boto3.client("s3")

RAW_BUCKET = os.environ["RAW_BUCKET"]   # e.g. "financial-reports-raw"


def lambda_handler(event, context):
    try:
        # API Gateway passes the file as base64-encoded body
        body        = event.get("body", "")
        is_b64      = event.get("isBase64Encoded", False)
        file_bytes  = base64.b64decode(body) if is_b64 else body.encode()

        # Extract metadata from query parameters
        params      = event.get("queryStringParameters") or {}
        company     = params.get("company", "unknown")
        report_year = params.get("year", str(datetime.utcnow().year))
        report_type = params.get("type", "annual")   # annual | quarterly

        if not file_bytes:
            return _response(400, {"error": "Empty file body"})

        if not file_bytes[:4] == b"%PDF":
            return _response(400, {"error": "File must be a PDF"})

        # Build S3 key:  raw/apple/2026/annual/uuid.pdf
        file_id = str(uuid.uuid4())
        s3_key  = f"raw/{company}/{report_year}/{report_type}/{file_id}.pdf"

        s3.put_object(
            Bucket=RAW_BUCKET,
            Key=s3_key,
            Body=file_bytes,
            ContentType="application/pdf",
            Metadata={
                "company":     company,
                "report_year": report_year,
                "report_type": report_type,
                "file_id":     file_id,
            },
        )

        print(f"Stored: s3://{RAW_BUCKET}/{s3_key}")

        return _response(200, {
            "file_id":  file_id,
            "s3_key":   s3_key,
            "message":  "Upload successful. Processing will begin shortly.",
        })

    except Exception as e:
        print(f"Error: {e}")
        return _response(500, {"error": str(e)})


def _response(status_code, body):
    return {
        "statusCode": status_code,
        "headers":    {"Content-Type": "application/json"},
        "body":       json.dumps(body),
    }
