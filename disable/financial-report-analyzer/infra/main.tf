# infra/main.tf
# Core AWS resources for the Financial Report Analyzer pipeline.
# Provisions: S3 buckets, IAM roles, Lambda functions, Step Functions.

provider "aws" {
  region = var.aws_region
}

# ── Variables ─────────────────────────────────────────────────────────────────

variable "aws_region"    { default = "ap-southeast-1" }
variable "project_name"  { default = "financial-report-analyzer" }
variable "opensearch_host" {
  description = "OpenSearch domain endpoint (no https://)"
}
variable "sagemaker_endpoint_name" {
  default = "bilstm-financial-classifier"
}

# ── S3 buckets ────────────────────────────────────────────────────────────────

resource "aws_s3_bucket" "raw" {
  bucket = "${var.project_name}-raw"
}

resource "aws_s3_bucket" "processed" {
  bucket = "${var.project_name}-processed"
}

resource "aws_s3_bucket" "models" {
  bucket = "${var.project_name}-models"
}

# Block all public access on all buckets
resource "aws_s3_bucket_public_access_block" "raw"       { bucket = aws_s3_bucket.raw.id;       block_public_acls = true; block_public_policy = true; ignore_public_acls = true; restrict_public_buckets = true }
resource "aws_s3_bucket_public_access_block" "processed" { bucket = aws_s3_bucket.processed.id; block_public_acls = true; block_public_policy = true; ignore_public_acls = true; restrict_public_buckets = true }

# Lifecycle: delete raw PDFs after 7 years (financial records retention)
resource "aws_s3_bucket_lifecycle_configuration" "raw" {
  bucket = aws_s3_bucket.raw.id
  rule {
    id     = "expire-raw-pdfs"
    status = "Enabled"
    filter { prefix = "raw/" }
    expiration { days = 2555 }   # 7 years
  }
}

# ── IAM role shared by all Lambda functions ───────────────────────────────────

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    effect    = "Allow"
    actions   = ["sts:AssumeRole"]
    principals { type = "Service"; identifiers = ["lambda.amazonaws.com"] }
  }
}

resource "aws_iam_role" "lambda_role" {
  name               = "${var.project_name}-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

data "aws_iam_policy_document" "lambda_permissions" {
  # S3: read raw, read+write processed
  statement {
    sid       = "ReadRaw"
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.raw.arn}/*"]
  }
  statement {
    sid       = "ReadWriteProcessed"
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${aws_s3_bucket.processed.arn}/*"]
  }
  # Textract
  statement {
    sid       = "Textract"
    effect    = "Allow"
    actions   = ["textract:DetectDocumentText", "textract:AnalyzeDocument"]
    resources = ["*"]
  }
  # OpenSearch
  statement {
    sid       = "OpenSearch"
    effect    = "Allow"
    actions   = ["es:ESHttpGet", "es:ESHttpPost", "es:ESHttpPut"]
    resources = ["*"]
  }
  # SageMaker inference (Stage 2 Lambda only)
  statement {
    sid       = "SageMakerInference"
    effect    = "Allow"
    actions   = ["sagemaker:InvokeEndpoint"]
    resources = ["*"]
  }
  # CloudWatch Logs
  statement {
    sid       = "Logs"
    effect    = "Allow"
    actions   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:aws:logs:${var.aws_region}:*:log-group:/aws/lambda/${var.project_name}*:*"]
  }
}

resource "aws_iam_role_policy" "lambda_permissions" {
  name   = "${var.project_name}-lambda-policy"
  role   = aws_iam_role.lambda_role.id
  policy = data.aws_iam_policy_document.lambda_permissions.json
}

# ── Lambda functions ──────────────────────────────────────────────────────────

locals {
  lambda_defaults = {
    role          = aws_iam_role.lambda_role.arn
    runtime       = "python3.12"
    timeout       = 300
    memory_size   = 512
    source_code_hash = filebase64sha256("lambda_functions.zip")
    filename      = "lambda_functions.zip"
  }
}

resource "aws_lambda_function" "ingestion" {
  function_name = "${var.project_name}-ingestion"
  handler       = "ingestion.lambda_handler.lambda_handler"
  role          = aws_iam_role.lambda_role.arn
  runtime       = "python3.12"
  timeout       = 30
  memory_size   = 256
  filename      = "lambda_functions.zip"

  environment {
    variables = { RAW_BUCKET = aws_s3_bucket.raw.id }
  }
}

resource "aws_lambda_function" "parsing" {
  function_name = "${var.project_name}-parsing"
  handler       = "parsing.lambda_handler.lambda_handler"
  role          = aws_iam_role.lambda_role.arn
  runtime       = "python3.12"
  timeout       = 300
  memory_size   = 1024
  filename      = "lambda_functions.zip"

  environment {
    variables = {
      PROCESSED_BUCKET = aws_s3_bucket.processed.id
      OPENSEARCH_HOST  = var.opensearch_host
      OPENSEARCH_INDEX = "annual-reports"
    }
  }
}

resource "aws_lambda_function" "stage1" {
  function_name = "${var.project_name}-stage1-retrieval"
  handler       = "stage1_retrieval.lambda_handler.lambda_handler"
  role          = aws_iam_role.lambda_role.arn
  runtime       = "python3.12"
  timeout       = 60
  memory_size   = 512
  filename      = "lambda_functions.zip"

  environment {
    variables = {
      OPENSEARCH_HOST  = var.opensearch_host
      OPENSEARCH_INDEX = "annual-reports"
    }
  }
}

resource "aws_lambda_function" "stage2" {
  function_name = "${var.project_name}-stage2-classification"
  handler       = "stage2_classification.lambda_handler.lambda_handler"
  role          = aws_iam_role.lambda_role.arn
  runtime       = "python3.12"
  timeout       = 120
  memory_size   = 512
  filename      = "lambda_functions.zip"

  environment {
    variables = {
      SAGEMAKER_ENDPOINT = var.sagemaker_endpoint_name
    }
  }
}

resource "aws_lambda_function" "assembly" {
  function_name = "${var.project_name}-assembly"
  handler       = "assembly.lambda_handler.lambda_handler"
  role          = aws_iam_role.lambda_role.arn
  runtime       = "python3.12"
  timeout       = 60
  memory_size   = 512
  filename      = "lambda_functions.zip"

  environment {
    variables = {
      PROCESSED_BUCKET = aws_s3_bucket.processed.id
    }
  }
}

# ── S3 trigger: raw bucket upload → parsing Lambda ────────────────────────────

resource "aws_lambda_permission" "s3_trigger" {
  statement_id  = "AllowS3Invoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.parsing.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.raw.arn
}

resource "aws_s3_bucket_notification" "raw_trigger" {
  bucket = aws_s3_bucket.raw.id
  lambda_function {
    lambda_function_arn = aws_lambda_function.parsing.arn
    events              = ["s3:ObjectCreated:*"]
    filter_suffix       = ".pdf"
  }
  depends_on = [aws_lambda_permission.s3_trigger]
}

# ── Outputs ───────────────────────────────────────────────────────────────────

output "raw_bucket"       { value = aws_s3_bucket.raw.id }
output "processed_bucket" { value = aws_s3_bucket.processed.id }
output "models_bucket"    { value = aws_s3_bucket.models.id }
