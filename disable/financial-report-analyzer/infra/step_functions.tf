# infra/step_functions.tf
# Step Functions state machine that orchestrates the two-stage NLP pipeline.
# Triggered after parsing completes, runs Stage 1 + Stage 2 for each metric,
# then calls the assembly Lambda to produce the final report.

data "aws_iam_policy_document" "sfn_assume" {
  statement {
    effect    = "Allow"
    actions   = ["sts:AssumeRole"]
    principals { type = "Service"; identifiers = ["states.amazonaws.com"] }
  }
}

resource "aws_iam_role" "sfn_role" {
  name               = "${var.project_name}-sfn-role"
  assume_role_policy = data.aws_iam_policy_document.sfn_assume.json
}

resource "aws_iam_role_policy" "sfn_invoke_lambda" {
  name = "${var.project_name}-sfn-invoke-lambda"
  role = aws_iam_role.sfn_role.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["lambda:InvokeFunction"]
      Resource = [
        aws_lambda_function.stage1.arn,
        aws_lambda_function.stage2.arn,
        aws_lambda_function.assembly.arn,
      ]
    }]
  })
}

# The state machine runs Stage1 + Stage2 for each metric in parallel,
# then assembles the report.
resource "aws_sfn_state_machine" "nlp_pipeline" {
  name     = "${var.project_name}-nlp-pipeline"
  role_arn = aws_iam_role.sfn_role.arn

  definition = jsonencode({
    Comment = "Two-stage NLP pipeline: keyword retrieval + text classification"
    StartAt = "ProcessAllMetrics"

    States = {

      # Run all metrics in parallel (Map state)
      ProcessAllMetrics = {
        Type     = "Map"
        ItemsPath = "$.metrics"        # ["sales", "ebitda", "depreciation", ...]
        MaxConcurrency = 5
        Iterator = {
          StartAt = "Stage1_KeywordRetrieval"
          States = {
            Stage1_KeywordRetrieval = {
              Type     = "Task"
              Resource = aws_lambda_function.stage1.arn
              Parameters = {
                "file_id.$" = "$.file_id"
                "metric.$"  = "$.metric"
              }
              Next = "Stage2_Classification"
            }
            Stage2_Classification = {
              Type     = "Task"
              Resource = aws_lambda_function.stage2.arn
              Parameters = {
                "file_id.$"    = "$.file_id"
                "metric.$"     = "$.metric"
                "candidates.$" = "$.candidates"
              }
              End = true
            }
          }
        }
        Next = "AssembleReport"
      }

      # Collect all Top-3 results and build the final report
      AssembleReport = {
        Type     = "Task"
        Resource = aws_lambda_function.assembly.arn
        End      = true
      }

    }
  })
}

output "sfn_arn" { value = aws_sfn_state_machine.nlp_pipeline.arn }
