"""
stage2_classification/deploy/upload_and_deploy.py
--------------------------------------------------
Uploads model.tar.gz to S3 and deploys the SageMaker Endpoint.
Run once. The endpoint stays running until you delete it.

Usage:
    pip install boto3 sagemaker
    python stage2_classification/deploy/upload_and_deploy.py
"""

import boto3
import sagemaker
from sagemaker.tensorflow import TensorFlowModel

REGION        = "ap-southeast-1"
BUCKET        = "financial-reports-models"      # your S3 bucket
S3_KEY        = "bilstm-classifier/model.tar.gz"
ENDPOINT_NAME = "bilstm-financial-classifier"
INSTANCE_TYPE = "ml.m5.xlarge"
TF_VERSION    = "2.12"
PY_VERSION    = "py310"
LOCAL_TARBALL = "stage2_classification/model/model.tar.gz"

# Step 1: upload
print(f"Uploading {LOCAL_TARBALL} → s3://{BUCKET}/{S3_KEY} ...")
boto3.client("s3", region_name=REGION).upload_file(
    LOCAL_TARBALL, BUCKET, S3_KEY
)
s3_uri = f"s3://{BUCKET}/{S3_KEY}"
print(f"Upload complete: {s3_uri}")

# Step 2: deploy
print(f"\nDeploying endpoint '{ENDPOINT_NAME}' (3–5 min) ...")

role = sagemaker.get_execution_role()
# If running locally replace with:
# role = "arn:aws:iam::YOUR_ACCOUNT_ID:role/SageMakerRole"

TensorFlowModel(
    model_data=s3_uri,
    role=role,
    entry_point="inference.py",
    source_dir="stage2_classification",   # SageMaker picks up inference.py from here
    framework_version=TF_VERSION,
    py_version=PY_VERSION,
).deploy(
    initial_instance_count=1,
    instance_type=INSTANCE_TYPE,
    endpoint_name=ENDPOINT_NAME,
)

print(f"\nEndpoint ready: {ENDPOINT_NAME}")
print("Next: run stage2_classification/test/test_endpoint.py")
