"""
stage2_classification/lambda_handler.py
----------------------------------------
Stage 2 Lambda: receives 100 candidates from Stage 1,
calls SageMaker Endpoint, returns Top-3 per metric.
Called by Step Functions.
"""

import boto3
import json
import os

runtime = boto3.client("sagemaker-runtime")

ENDPOINT_NAME = os.environ["SAGEMAKER_ENDPOINT"]   # bilstm-financial-classifier


def lambda_handler(event, context):
    file_id    = event["file_id"]
    metric     = event["metric"]
    candidates = event["candidates"]   # 100 sentences from Stage 1

    sentences = [c["text"] for c in candidates]

    print(f"Stage 2 — file: {file_id}, metric: {metric}, candidates: {len(sentences)}")

    # Call SageMaker Endpoint
    response = runtime.invoke_endpoint(
        EndpointName=ENDPOINT_NAME,
        ContentType="application/json",
        Body=json.dumps({"sentences": sentences}),
    )
    results = json.loads(response["Body"].read())

    # Attach page numbers back from Stage 1 metadata
    for i, r in enumerate(results):
        r["page"] = candidates[i].get("page")

    # Sort by confidence → Top 3
    ranked = sorted(results, key=lambda x: x["confidence"], reverse=True)
    top3   = ranked[:3]

    print(f"  Top-3 confidence scores: {[round(r['confidence'],4) for r in top3]}")

    return {
        "statusCode": 200,
        "file_id":    file_id,
        "metric":     metric,
        "top3": [
            {
                "sentence":    r["text"],
                "page":        r["page"],
                "probability": r["confidence"],
            }
            for r in top3
        ],
    }
