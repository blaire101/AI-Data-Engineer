# infra/main.tf
# Core AWS resources for the Financial Report Analyzer.
# Two Lambda functions only:
#   1. ingestion  — receives PDF upload, writes to S3 raw
#   2. pipeline   — runs the full NLP flow (Textract → OpenSearch → SageMaker → report.html)

provider "aws" {
  region = var.aws_region
}

# ── Variables ─────────────────────────────────────────────────────────────────
variable "aws_region"    { default = "ap-southeast-1" }
variable "project_name"  { default = "financial-report-analyzer" }
variable "opensearch_host" {
  description = "OpenSearch domain endpoint (without https://)"
}
variable "sagemaker_endpoint_name" {
  default = "keras-financial-classifier"
}

# ── S3 buckets ────────────────────────────────────────────────────────────────
resource "aws_s3_bucket" "raw" {
  bucket = "${var.project_name}-raw"
}

resource "aws_s3_bucket" "analytics" {
  bucket = "${var.project_name}-analytics"
}

resource "aws_s3_bucket" "models" {
  bucket = "${var.project_name}-models"
}

# Block all public access
resource "aws_s3_bucket_public_access_block" "raw" {
  bucket                  = aws_s3_bucket.raw.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_public_access_block" "analytics" {
  bucket                  = aws_s3_bucket.analytics.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ── IAM role for Lambda ───────────────────────────────────────────────────────
data "aws_iam_policy_document" "lambda_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda_role" {
  name               = "${var.project_name}-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

data "aws_iam_policy_document" "lambda_permissions" {
  # S3: read raw, write analytics
  statement {
    sid     = "ReadRaw"
    effect  = "Allow"
    actions = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.raw.arn}/*"]
  }
  statement {
    sid     = "WriteAnalytics"
    effect  = "Allow"
    actions = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.analytics.arn}/*"]
  }
  statement {
    sid     = "WriteRaw"
    effect  = "Allow"
    actions = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.raw.arn}/*"]
  }
  # Textract
  statement {
    sid     = "Textract"
    effect  = "Allow"
    actions = ["textract:DetectDocumentText", "textract:AnalyzeDocument"]
    resources = ["*"]
  }
  # OpenSearch
  statement {
    sid     = "OpenSearch"
    effect  = "Allow"
    actions = ["es:ESHttpGet", "es:ESHttpPost", "es:ESHttpPut"]
    resources = ["*"]
  }
  # SageMaker inference
  statement {
    sid     = "SageMaker"
    effect  = "Allow"
    actions = ["sagemaker:InvokeEndpoint"]
    resources = ["*"]
  }
  # CloudWatch Logs
  statement {
    sid     = "Logs"
    effect  = "Allow"
    actions = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:aws:logs:${var.aws_region}:*:log-group:/aws/lambda/${var.project_name}*:*"]
  }
}

resource "aws_iam_role_policy" "lambda_permissions" {
  name   = "${var.project_name}-lambda-policy"
  role   = aws_iam_role.lambda_role.id
  policy = data.aws_iam_policy_document.lambda_permissions.json
}

# ── Lambda 1: Ingestion ───────────────────────────────────────────────────────
resource "aws_lambda_function" "ingestion" {
  function_name = "${var.project_name}-ingestion"
  handler       = "ingestion.lambda_handler.lambda_handler"
  role          = aws_iam_role.lambda_role.arn
  runtime       = "python3.12"
  timeout       = 30
  memory_size   = 256
  filename      = "lambda_functions.zip"

  environment {
    variables = {
      RAW_BUCKET = aws_s3_bucket.raw.id
    }
  }
}

# ── Lambda 2: Pipeline (main — Textract → OpenSearch → SageMaker → report) ───
resource "aws_lambda_function" "pipeline" {
  function_name = "${var.project_name}-pipeline"
  handler       = "pipeline.lambda_handler.lambda_handler"
  role          = aws_iam_role.lambda_role.arn
  runtime       = "python3.12"
  timeout       = 900       # 15 minutes — enough for any annual report
  memory_size   = 1024
  filename      = "lambda_functions.zip"

  environment {
    variables = {
      OPENSEARCH_HOST    = var.opensearch_host
      OPENSEARCH_INDEX   = "annual-reports"
      SAGEMAKER_ENDPOINT = var.sagemaker_endpoint_name
      ANALYTICS_BUCKET   = aws_s3_bucket.analytics.id
    }
  }
}

# ── API Gateway → Ingestion Lambda ────────────────────────────────────────────
resource "aws_api_gateway_rest_api" "api" {
  name = "${var.project_name}-api"
  binary_media_types = ["application/pdf"]
}

resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ingestion.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.api.execution_arn}/*/*"
}

# ── S3 trigger: raw bucket PDF upload → pipeline Lambda ──────────────────────
resource "aws_lambda_permission" "s3_trigger" {
  statement_id  = "AllowS3Invoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.pipeline.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.raw.arn
}

resource "aws_s3_bucket_notification" "raw_trigger" {
  bucket = aws_s3_bucket.raw.id
  lambda_function {
    lambda_function_arn = aws_lambda_function.pipeline.arn
    events              = ["s3:ObjectCreated:*"]
    filter_suffix       = ".pdf"
  }
  depends_on = [aws_lambda_permission.s3_trigger]
}

# ── Outputs ───────────────────────────────────────────────────────────────────
output "raw_bucket"       { value = aws_s3_bucket.raw.id }
output "analytics_bucket" { value = aws_s3_bucket.analytics.id }
output "models_bucket"    { value = aws_s3_bucket.models.id }
output "api_endpoint"     { value = aws_api_gateway_rest_api.api.id }
