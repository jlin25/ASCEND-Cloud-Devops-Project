import os
import json
import boto3


class JobQueue:
    def __init__(self):
        self.queue_url = os.getenv("SQS_QUEUE_URL")
        # boto3 reads AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY from the env automatically
        self.sqs = boto3.client("sqs", region_name=os.getenv("AWS_REGION", "us-east-1"))

    def send(self, body: dict) -> None:
        """Producer: put a job on the queue."""
        self.sqs.send_message(
            QueueUrl=self.queue_url,
            MessageBody=json.dumps(body),
        )

    def receive(self) -> list[dict]:
        """Consumer: long-poll for up to 10 messages, waiting up to 20s."""
        resp = self.sqs.receive_message(
            QueueUrl=self.queue_url,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=20,
            AttributeNames=["ApproximateReceiveCount"],
        )
        return resp.get("Messages", [])  # empty list if nothing's there

    def delete(self, receipt_handle: str) -> None:
        """Acknowledge: remove a message AFTER it processed successfully."""
        self.sqs.delete_message(
            QueueUrl=self.queue_url,
            ReceiptHandle=receipt_handle,
        )
