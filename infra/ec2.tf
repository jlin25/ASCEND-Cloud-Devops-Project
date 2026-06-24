# EC2 worker — runs worker.py, long-polling the SQS jobs queue.
#
# Unlike the local-dev IAM user (iam.tf), this box gets its permissions from an
# *instance role*: AWS injects temporary credentials automatically, so there are
# no access keys to manage or leak. The role can:
#   - send/receive/delete on the job queues   (jobs_access policy, iam.tf)
#   - read runtime config from SSM            (ssm_read policy, iam.tf)
#   - be managed via Session Manager          (AmazonSSMManagedInstanceCore)

# Latest Amazon Linux 2023 AMI for the region — avoids hardcoding an AMI id.
data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }
  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# --- Instance role + profile ----------------------------------------------
data "aws_iam_policy_document" "ec2_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "worker" {
  name               = "${var.project_name}-worker"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
}

resource "aws_iam_role_policy_attachment" "worker_jobs_access" {
  role       = aws_iam_role.worker.name
  policy_arn = aws_iam_policy.jobs_access.arn
}

resource "aws_iam_role_policy_attachment" "worker_ssm_read" {
  role       = aws_iam_role.worker.name
  policy_arn = aws_iam_policy.ssm_read.arn
}

# Enables Session Manager ("aws ssm start-session") so we can get a shell on the
# box without opening SSH / port 22. Matches the session-manager-plugin prereq
# checked in init.sh.
resource "aws_iam_role_policy_attachment" "worker_ssm_core" {
  role       = aws_iam_role.worker.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "worker" {
  name = "${var.project_name}-worker"
  role = aws_iam_role.worker.name
}

# --- Network ---------------------------------------------------------------
# No inbound rules: all access is via Session Manager over the instance's
# outbound HTTPS. Egress is open so the worker can reach SQS, SSM, and Supabase.
resource "aws_security_group" "worker" {
  name        = "${var.project_name}-worker"
  description = "Egress-only SG for the ${var.project_name} worker (managed via SSM)."

  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.project_name}-worker" }
}

# --- The instance ----------------------------------------------------------
resource "aws_instance" "worker" {
  ami                    = data.aws_ami.al2023.id
  instance_type          = var.instance_type
  iam_instance_profile   = aws_iam_instance_profile.worker.name
  vpc_security_group_ids = [aws_security_group.worker.id]

  user_data = templatefile("${path.module}/user_data.sh.tftpl", {
    region      = var.aws_region
    ssm_prefix  = "/${var.project_name}"
    repo_url    = var.worker_repo_url
    repo_branch = var.worker_branch
  })

  # Re-run user_data if the template changes (otherwise it only runs at first
  # boot). Cheap for a single dev worker; drop this for a long-lived fleet.
  user_data_replace_on_change = true

  tags = { Name = "${var.project_name}-worker" }
}
