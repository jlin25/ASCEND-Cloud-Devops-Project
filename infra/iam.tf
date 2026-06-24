# Least-privilege policy: the app can ONLY send/receive/delete on these two
# queues. It deliberately cannot create/delete queues — that's Terraform's job.
data "aws_iam_policy_document" "jobs_access" {
  statement {
    sid    = "JobQueueAccess"
    effect = "Allow"
    actions = [
      "sqs:SendMessage",
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
    ]
    resources = [
      aws_sqs_queue.jobs.arn,
      aws_sqs_queue.jobs_dlq.arn,
    ]
  }
}

resource "aws_iam_policy" "jobs_access" {
  name        = "${var.project_name}-jobs-access"
  description = "Minimal SQS access for the ${var.project_name} backend."
  policy      = data.aws_iam_policy_document.jobs_access.json
}

# A dedicated IAM user for local development. On real AWS infrastructure
# (EC2/ECS/Lambda) you'd attach `jobs_access` to a ROLE instead and skip the
# access keys entirely — credentials would be injected automatically.
resource "aws_iam_user" "app" {
  name = "${var.project_name}-backend"
}

resource "aws_iam_user_policy_attachment" "app_jobs_access" {
  user       = aws_iam_user.app.name
  policy_arn = aws_iam_policy.jobs_access.arn
}

resource "aws_iam_access_key" "app" {
  user = aws_iam_user.app.name
}

# --- SSM Parameter Store ---------------------------------------------------
# Runtime config for the EC2 worker. The worker's instance role can read every
# parameter under /${var.project_name}/* (see ec2.tf). Secrets are SecureString
# (encrypted with the AWS-managed aws/ssm KMS key); non-secrets are plain String.
resource "aws_ssm_parameter" "queue_url" {
  name  = "/${var.project_name}/queue_url"
  type  = "String"
  value = aws_sqs_queue.jobs.url
}

resource "aws_ssm_parameter" "dlq_url" {
  name  = "/${var.project_name}/dlq_url"
  type  = "String"
  value = aws_sqs_queue.jobs_dlq.url
}

resource "aws_ssm_parameter" "aws_region" {
  name  = "/${var.project_name}/aws_region"
  type  = "String"
  value = var.aws_region
}

resource "aws_ssm_parameter" "db_url" {
  name  = "/${var.project_name}/db_url"
  type  = "SecureString"
  value = var.db_url
}

resource "aws_ssm_parameter" "db_service_key" {
  name  = "/${var.project_name}/db_service_key"
  type  = "SecureString"
  value = var.db_service_key
}

# Read-only access to the parameters above, granted to the worker's instance
# role. Scoped to this project's prefix so the worker can't read other secrets.
data "aws_iam_policy_document" "ssm_read" {
  statement {
    sid    = "ReadProjectParameters"
    effect = "Allow"
    actions = [
      "ssm:GetParameter",
      "ssm:GetParameters",
      "ssm:GetParametersByPath",
    ]
    resources = [
      "arn:aws:ssm:${var.aws_region}:*:parameter/${var.project_name}/*",
    ]
  }

  # Decrypt the SecureString values. The AWS-managed aws/ssm key delegates
  # access to IAM, so this statement is what actually authorizes decryption.
  statement {
    sid       = "DecryptSecureStrings"
    effect    = "Allow"
    actions   = ["kms:Decrypt"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["ssm.${var.aws_region}.amazonaws.com"]
    }
  }
}

resource "aws_iam_policy" "ssm_read" {
  name        = "${var.project_name}-ssm-read"
  description = "Read ${var.project_name} runtime config from SSM Parameter Store."
  policy      = data.aws_iam_policy_document.ssm_read.json
}
