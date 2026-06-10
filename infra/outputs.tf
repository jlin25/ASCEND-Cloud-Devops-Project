# Paste this into backend/.env as SQS_QUEUE_URL
output "queue_url" {
  description = "URL of the main jobs queue."
  value       = aws_sqs_queue.jobs.url
}

output "dlq_url" {
  description = "URL of the dead-letter queue."
  value       = aws_sqs_queue.jobs_dlq.url
}

output "aws_region" {
  description = "Region the queues live in."
  value       = var.aws_region
}

# Credentials for the local-dev IAM user. Marked sensitive so they aren't
# printed by default. Retrieve them with:
#   terraform output -raw app_access_key_id
#   terraform output -raw app_secret_access_key
output "app_access_key_id" {
  description = "Access key id for the backend IAM user."
  value       = aws_iam_access_key.app.id
  sensitive   = true
}

output "app_secret_access_key" {
  description = "Secret access key for the backend IAM user."
  value       = aws_iam_access_key.app.secret
  sensitive   = true
}
