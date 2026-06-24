variable "aws_region" {
  description = "AWS region to create resources in."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Prefix used to name resources so they're easy to find/destroy."
  type        = string
  default     = "ascend"
}

variable "visibility_timeout_seconds" {
  description = "How long a received message stays hidden before reappearing. Set this LONGER than your worker's max processing time."
  type        = number
  default     = 60
}

variable "max_receive_count" {
  description = "Number of delivery attempts before a message is sent to the dead-letter queue."
  type        = number
  default     = 3
}

# --- Secrets pushed into SSM Parameter Store ------------------------------
# These are read by the EC2 worker at boot (see ec2.tf / user_data.sh.tftpl).
# Pass them in via terraform.tfvars or TF_VAR_* env vars — never commit real
# values. Empty defaults let `plan` run without them, but the worker won't be
# able to reach Supabase until they're set.
variable "db_url" {
  description = "Supabase Postgres URL (stored as a SecureString in SSM)."
  type        = string
  default     = ""
  sensitive   = true
}

variable "db_service_key" {
  description = "Supabase service-role key (stored as a SecureString in SSM)."
  type        = string
  default     = ""
  sensitive   = true
}

# --- EC2 worker -----------------------------------------------------------
variable "instance_type" {
  description = "EC2 instance type for the worker. t3.micro is free-tier eligible."
  type        = string
  default     = "t3.micro"
}

variable "worker_repo_url" {
  description = "Git URL of this repo. If set, user_data clones it and runs worker.py as a systemd service. Leave empty to provision the box without deploying code."
  type        = string
  default     = ""
}

variable "worker_branch" {
  description = "Branch to deploy on the worker."
  type        = string
  default     = "main"
}
