import os
import sys

# Make the backend modules (jobs, worker, main, routers, ...) importable when
# pytest is run from anywhere.
sys.path.insert(0, os.path.dirname(__file__))

# Harmless defaults .
os.environ.setdefault("DB_URL", "https://test.supabase.co")
os.environ.setdefault("DB_SERVICE_KEY", "test-service-key")
os.environ.setdefault("S3_BUCKET_NAME", "test-bucket")
os.environ.setdefault("AWS_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault(
    "SQS_QUEUE_URL", "https://sqs.us-east-1.amazonaws.com/000000000000/test"
)
os.environ.setdefault("SECRET_KEY", "test-secret")
