import json
from job_queue import JobQueue
from db.client import database
from jobs import JobRequest, TranscodeJob, TrimJob, ExtractAudioJob, job_adapter

queue = JobQueue()


def handle(job: JobRequest):
    match job:
        case TranscodeJob():
            pass  # transcode logic here
        case TrimJob():
            pass  # trim logic here
        case ExtractAudioJob():
            pass  # extract audio logic here


def run():
    print("worker started, polling for jobs...")
    while True:
        for msg in queue.receive():
            body = json.loads(msg["body"])
            job_id = body["job_id"]
            try:
                database.table("jobs").update({"status": "processing"}).eq(
                    "id", job_id
                ).execute()
                job = job_adapter.validate_python(body)
                handle(job)
                database.table("jobs").update({"status": "done"}).eq(
                    "id", job_id
                ).execute()
                queue.delete(msg["receipthandle"])
            except Exception as e:
                print(f"job {job_id} failed, will be retried: {e}")
                database.table("jobs").update({"status": "failed"}).eq(
                    "id", job_id
                ).execute()


if __name__ == "__main__":
    run()
