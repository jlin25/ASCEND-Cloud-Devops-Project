import json
import mimetypes
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
    ImageResizeJob,
    FormatConverterJob,
    job_adapter,
)
from s3_client import S3Client
from typing import assert_never

queue = JobQueue()
s3 = S3Client()

_HEIGHT = {"720p": 720, "1080p": 1080, "4k": 2160}


# mkstemp instead of NamedTemporaryFile for src/dst: ffmpeg needs to open
# these paths itself (as the input and as the output), and on Windows a
# NamedTemporaryFile's own handle stays open/locked for the whole `with`
# block, so a second process opening the same path fails with
# PermissionError ("Error opening input: Permission denied" from ffmpeg).
# mkstemp lets us close our handle before ffmpeg ever touches the file.


def process_video_quality(job: VideoQualityJob, user_id: str) -> str:
    height = _HEIGHT[job.resolution]
    suffix = os.path.splitext(job.file_url)[1] or ".mp4"

    src_fd, src_path = tempfile.mkstemp(suffix=suffix)
    dst_fd, dst_path = tempfile.mkstemp(suffix=".mp4")
    os.close(dst_fd)
    try:
        with os.fdopen(src_fd, "wb") as src:
            body = s3.download_stream(job.file_url)
            for chunk in body.iter_chunks():
                src.write(chunk)

        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                src_path,
                "-vf",
                f"scale=-2:{height}",
                "-c:v",
                "libx264",
                "-crf",
                "23",
                "-c:a",
                "aac",
                dst_path,
            ],
            check=True,
            capture_output=True,
        )

        filename = os.path.basename(job.file_url)
        with open(dst_path, "rb") as out:
            return s3.upload_stream(
                user_id, filename, out, "video/mp4", prefix="processed"
            )
    finally:
        os.remove(src_path)
        os.remove(dst_path)


def process_image_resize(job: ImageResizeJob, user_id: str) -> str:
    suffix = os.path.splitext(job.file_url)[1] or ".jpg"

    src_fd, src_path = tempfile.mkstemp(suffix=suffix)
    dst_fd, dst_path = tempfile.mkstemp(suffix=suffix)
    os.close(dst_fd)
    try:
        with os.fdopen(src_fd, "wb") as src:
            body = s3.download_stream(job.file_url)
            for chunk in body.iter_chunks():
                src.write(chunk)

        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                src_path,
                "-vf",
                f"scale={job.width}:{job.height}",
                "-update",
                "1",
                dst_path,
            ],
            check=True,
            capture_output=True,
        )

        content_type = (
            mimetypes.guess_type(job.file_url)[0] or "application/octet-stream"
        )
        filename = os.path.basename(job.file_url)
        with open(dst_path, "rb") as out:
            return s3.upload_stream(
                user_id, filename, out, content_type, prefix="processed"
            )
    finally:
        os.remove(src_path)
        os.remove(dst_path)

def convert_format(job: FormatConverterJob, user_id: str) -> str:
    src_suffix = f".{job.input_format}"
    dst_suffix = f".{job.output_format}"

    src_fd, src_path = tempfile.mkstemp(suffix=src_suffix)
    dst_fd, dst_path = tempfile.mkstemp(suffix=dst_suffix)
    os.close(dst_fd)
    try:
        with os.fdopen(src_fd, "wb") as src:
            body = s3.download_stream(job.file_url)
            for chunk in body.iter_chunks():
                src.write(chunk)

        subprocess.run(
            ["ffmpeg", "-y", "-i", src_path, dst_path],
            check=True,
            capture_output=True,
        )

        content_type = mimetypes.guess_type(dst_path)[0] or "application/octet-stream"
        filename = os.path.basename(job.file_url)
        with open(dst_path, "rb") as out:
            return s3.upload_stream(
                user_id, filename, out, content_type, prefix="processed"
            )
    finally:
        os.remove(src_path)
        os.remove(dst_path)



def process_trim(job: TrimJob, user_id: str) -> str:
    suffix = os.path.splitext(job.file_url)[1] or ".mp4"

    src_fd, src_path = tempfile.mkstemp(suffix=suffix)
    dst_fd, dst_path = tempfile.mkstemp(suffix=suffix)
    os.close(dst_fd)
    try:
        with os.fdopen(src_fd, "wb") as src:
            body = s3.download_stream(job.file_url)
            for chunk in body.iter_chunks():
                src.write(chunk)

        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                src_path,
                "-ss",
                str(job.start_seconds),
                "-to",
                str(job.end_seconds),
                "-c",
                "copy",
                dst_path,
            ],
            check=True,
            capture_output=True,
        )

        content_type = (
            mimetypes.guess_type(job.file_url)[0] or "application/octet-stream"
        )
        filename = os.path.basename(job.file_url)
        with open(dst_path, "rb") as out:
            return s3.upload_stream(
                user_id, filename, out, content_type, prefix="processed"
            )
    finally:
        os.remove(src_path)
        os.remove(dst_path)


def handle(job: JobRequest, user_id: str) -> str | None:
    match job:
        case TranscodeJob():
            pass  # transcode logic here
        case TrimJob():
            return process_trim(job, user_id)
        case ExtractAudioJob():
            pass  # extract audio logic here
        case VideoQualityJob():
            return process_video_quality(job, user_id)
        case ImageResizeJob():
            return process_image_resize(job, user_id)
        case FormatConverterJob():
            return convert_format(job, user_id)
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
