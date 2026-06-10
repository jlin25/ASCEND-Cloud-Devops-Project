Install aws cli
aws login
eval "$(aws configure export-credentials --format env)"
terraform init
terraform plan
terraform apply
cd infra
{
  echo "SQS_QUEUE_URL=$(terraform output -raw queue_url)"
  echo "SQS_DLQ_URL=$(terraform output -raw dlq_url)"
  echo "AWS_REGION=$(terraform output -raw aws_region)"
  echo "AWS_ACCESS_KEY_ID=$(terraform output -raw app_access_key_id)"
  echo "AWS_SECRET_ACCESS_KEY=$(terraform output -raw app_secret_access_key)"
} >> ../backend/.env
when done, terraform destroy
