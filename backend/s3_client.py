import boto3
import os

class S3Client:
    def __init__(self):
        self.bucket = os.getenv("S3_BUCKET_NAME")
        self.client = boto3.client("s3", region_name=os.getenv("AWS_REGION"))
    
    def upload_stream(self,filename : str, file, content_type : str) -> str:
        key = f"uploads/{filename}"
        self.client.upload_fileobj(
            file.file,
            self.bucket,
            key,
            ExtraArgs={"ContentType": content_type}
        )
        return key
    
    def copy_to_processing(self, upload_key: str) -> str:
        filename = upload_key.split("/")[-1]
        processing_key = f"processing/{filename}"
        self.client.copy_object(
            Bucket=self.bucket,
            CopySource={"Bucket": self.bucket, "Key": upload_key},
            Key=processing_key,
        )
        return processing_key
    
    def get_output_url(self, key : str, expires_in int = 24 * 3600) -> str: #link available for one day
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_in,
        )
    
    def delete_from_processing(self, key: str):
        if not key.startswith("processing/"):
            raise ValueError(f"Will not delete outside processing/: {key}")
        self.client.delete_object(Bucket=self.bucket, Key=key)
    

