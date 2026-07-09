# Paste this into backend/.env as SQS_QUEUE_URL
output "queue_url" {
  description = "URL of the main jobs queue."
  value       = aws_sqs_queue.jobs.url
}

output "dlq_url" {
  description = "URL of the dead-letter queue."
  value       = aws_sqs_queue.jobs_dlq.url
}

# S3_BUCKET_NAME in env
output "bucket_name" {
  description = "Name of the S3 file storage bucket"
  value = aws_s3_bucket.file_storage.bucket
}

output "aws_region" {
  description = "Region the queues and S3 live in."
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

# --- EC2 worker ------------------------------------------------------------
output "worker_instance_id" {
  description = "EC2 instance id of the worker. Get a shell with: aws ssm start-session --target <id>"
  value       = aws_instance.worker.id
}

output "worker_public_ip" {
  description = "Public IP of the worker (for debugging; access is normally via SSM)."
  value       = aws_instance.worker.public_ip
}
