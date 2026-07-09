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
