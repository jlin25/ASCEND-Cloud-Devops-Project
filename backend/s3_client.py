import boto3
import os

class S3Client:
    def __init__(self):
        self.bucket = os.getenv("S3_BUCKET_NAME")
        self.client = boto3.client("s3", region_name=os.getenv("AWS_REGION"))
    
    def upload_stream(self,filename : str, file, content_type : str, prefix: str = "uploads") -> str:
        #by default returns uploads key, otherwise set prefix="processed" to get key
        key = f"{prefix}/{filename}"
        self.client.upload_fileobj(
            file,
            self.bucket,
            key,
            ExtraArgs={"ContentType": content_type}
        )
        return key
    
    def download_stream(self, input_key: str):
        # returns StreamingBody (not in memory yet) — call .read() to load full file, or .iter_chunks() to process in chunks without loading all at once
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        return response["Body"]
    
    def get_output_url(self, key : str, expires_in int = 24 * 3600) -> str: #link available for one day
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_in,
        )
    
    def delete_object(self, key: str):
        self.client.delete_object(Bucket=self.bucket, Key=key)
    

