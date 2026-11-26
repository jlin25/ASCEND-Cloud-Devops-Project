import re
import uuid
import boto3
import os

# Keys are <prefix>/<userid>/<uuid>-<filename>, and <filename> for an output key is named after the uuid + original filename of the input key.
_UUID_PREFIXES = re.compile(r"^(?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}-)+", re.I)


def original_name(key: str) -> str:
    name = key.rsplit("/", 1)[-1]
    return _UUID_PREFIXES.sub("", name) or name


class S3Client:
    def __init__(self):
        self.bucket = os.getenv("S3_BUCKET_NAME")
        self.client = boto3.client("s3", region_name=os.getenv("AWS_REGION"))

    def upload_stream(self, user_id: str, filename : str, file, content_type : str, prefix: str = "uploads") -> str:
        #by default returns uploads key, otherwise set prefix="processed" to get key
        key = f"{prefix}/{user_id}/{uuid.uuid4()}-{filename}"
        self.client.upload_fileobj(
            file,
            self.bucket,
            key,
            ExtraArgs={"ContentType": content_type}
        )
        return key

    def download_stream(self, input_key: str):
        # returns StreamingBody (not in memory yet) — call .read() to load full file, or .iter_chunks() to process in chunks without loading all at once
        response = self.client.get_object(Bucket=self.bucket, Key=input_key)
        return response["Body"]

    def get_output_url(self, key : str, expires_in: int = 24 * 3600, download_name: str | None = None) -> str: #link available for one day
        params = {"Bucket": self.bucket, "Key": key}
        if download_name:
            # Makes the browser save the file under this name instead of the raw key.
            params["ResponseContentDisposition"] = f'attachment; filename="{download_name}"'
        return self.client.generate_presigned_url(
            "get_object",
            Params=params,
            ExpiresIn=expires_in,
        )

    def delete_object(self, key: str):
        self.client.delete_object(Bucket=self.bucket, Key=key)

