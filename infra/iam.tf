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

  statement {
    sid = "FileStorageAccess"
    effect = "Allow"
    actions = [
      "s3.PutObject",
      "s3.GetObject",
      "s3.CopyObject",
    ]
    resources = [
      aws_s3_bucket.file_storage.arn,
      "${aws_s3_bucket.file_storage.arn}/*",
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
