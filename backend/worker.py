import json
import os
import subprocess
import tempfile
from job_queue import JobQueue
from db.client import database
from jobs import (
    JobRequest,
    TranscodeJob,
    TrimJob,
    ExtractAudioJob,
    VideoQualityJob,
    job_adapter,
)
from s3_client import S3Client
from typing import assert_never

queue = JobQueue()
s3 = S3Client()

_HEIGHT = {"720p": 720, "1080p": 1080, "4k": 2160}


def process_video_quality(job: VideoQualityJob, user_id: str) -> str:
    height = _HEIGHT[job.resolution]
    suffix = os.path.splitext(job.file_url)[1] or ".mp4"

    with (
        tempfile.NamedTemporaryFile(suffix=suffix) as src,
        tempfile.NamedTemporaryFile(suffix=".mp4") as dst,
    ):
        body = s3.download_stream(job.file_url)
        for chunk in body.iter_chunks():
            src.write(chunk)
        src.flush()

        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                src.name,
                "-vf",
                f"scale=-2:{height}",
                "-c:v",
                "libx264",
                "-crf",
                "23",
                "-c:a",
                "aac",
                dst.name,
            ],
            check=True,
            capture_output=True,
        )

        filename = os.path.basename(job.file_url)
        with open(dst.name, "rb") as out:
            return s3.upload_stream(
                user_id, filename, out, "video/mp4", prefix="processed"
            )


def handle(job: JobRequest, user_id: str) -> str | None:
    match job:
        case TranscodeJob():
            pass  # transcode logic here
        case TrimJob():
            pass  # trim logic here
        case ExtractAudioJob():
            pass  # extract audio logic here
        case VideoQualityJob():
            return process_video_quality(job, user_id)
        case _:
            assert_never(job)


def run():
    print("worker started, polling for jobs...")
    while True:
        for msg in queue.receive():
            body = json.loads(msg["Body"])
            job_id = body["job_id"]
            user_id = body["user_id"]
            try:
                database.table("jobs").update({"status": "processing"}).eq(
                    "id", job_id
                ).execute()
                job = job_adapter.validate_python(body)
                output_key = handle(job, user_id)
                database.table("jobs").update(
                    {
                        "status": "done",
                        "progress": 100,
                        "output_key": output_key,
                    }
                ).eq("id", job_id).execute()
                queue.delete(msg["ReceiptHandle"])
            except Exception as e:
                print(f"job {job_id} failed, will be retried: {e}")
                database.table("jobs").update({"status": "failed"}).eq(
                    "id", job_id
                ).execute()


if __name__ == "__main__":
    run()
