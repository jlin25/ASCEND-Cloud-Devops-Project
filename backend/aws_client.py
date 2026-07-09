#Establish a connection to S3. Import in files that need to upload/download files
#For example, in a file under backend folder, import with "from aws_client import s3_client, BUCKET_NAME"
import os
from dotenv import load_dotenv
import boto3

load_dotenv()
s3_client = boto3.client(
    "s3",
    region_name=os.getenv("AWS_REGION"),
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
)
BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
