import json
import math
import mimetypes
import os
import subprocess
import tempfile
import threading
import time
from contextvars import ContextVar
from job_queue import JobQueue
from db.client import database
from jobs import (
    JobRequest,
    TranscodeJob,
    TrimJob,
    ExtractAudioJob,
    VideoQualityJob,
    ImageResizeJob,
    DeblurJob,
    FormatConverterJob,
    TranscribeJob,
    job_adapter,
    VIDEO_FORMATS,
)
from s3_client import S3Client
from typing import assert_never
import cv2
import numpy as np
from huggingface_hub import hf_hub_download

queue = JobQueue()
s3 = S3Client()

_HEIGHT = {"720p": 720, "1080p": 1080, "4k": 2160}

# extract_audio: ffmpeg codec args and the content type for each output format.
_AUDIO = {
    "mp3": (["-c:a", "libmp3lame", "-q:a", "2"], "audio/mpeg"),
    "wav": (["-c:a", "pcm_s16le"], "audio/wav"),
    "aac": (["-c:a", "aac", "-b:a", "192k"], "audio/aac"),
}


deblur_model_path = hf_hub_download(
    repo_id="opencv/deblurring_nafnet",
    filename="deblurring_nafnet_2025may.onnx",
)

deblur_net = cv2.dnn.readNet(deblur_model_path)
# mkstemp instead of NamedTemporaryFile for src/dst: ffmpeg needs to open
# these paths itself (as the input and as the output), and on Windows a
# NamedTemporaryFile's own handle stays open/locked for the whole `with`
# block, so a second process opening the same path fails with
# PermissionError ("Error opening input: Permission denied" from ffmpeg).
# mkstemp lets us close our handle before ffmpeg ever touches the file.

# --- Visibility heartbeat ----------------------------------------------------
# SQS hides a received message for the queue's visibility timeout (60s in
# infra/variables.tf); if the job isn't finished by then, another worker picks
# it up too. While a job is visibly making progress we keep pushing that
# deadline out. A job that stops progressing (hung ffmpeg, stuck download)
# stops being extended, so SQS redelivers it once the current timeout lapses.
VISIBILITY_EXTENSION_SECONDS = int(os.getenv("VISIBILITY_EXTENSION_SECONDS", "60"))
HEARTBEAT_INTERVAL_SECONDS = int(os.getenv("HEARTBEAT_INTERVAL_SECONDS", "20"))
STALL_TIMEOUT_SECONDS = int(os.getenv("STALL_TIMEOUT_SECONDS", "60"))
# The deblur model is a single opaque forward() call with no progress to
# observe, so it gets a fixed grace period instead.
DEBLUR_GRACE_SECONDS = int(os.getenv("DEBLUR_GRACE_SECONDS", "600"))


class Heartbeat:
    """Extends a message's visibility for as long as beat() keeps being called."""

    def __init__(self, receipt_handle: str):
        self.receipt_handle = receipt_handle
        self._last_beat = time.monotonic()
        self._grace_until = 0.0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def beat(self, grace: float = 0) -> None:
        """Record progress. `grace` covers a step whose progress can't be seen."""
        now = time.monotonic()
        self._last_beat = now
        self._grace_until = max(self._grace_until, now + grace)

    def progressing(self) -> bool:
        now = time.monotonic()
        return now - self._last_beat < STALL_TIMEOUT_SECONDS or now < self._grace_until

    def _run(self) -> None:
        while not self._stop.wait(HEARTBEAT_INTERVAL_SECONDS):
            if not self.progressing():
                print("no progress seen, letting message visibility lapse")
                return
            try:
                queue.extend(self.receipt_handle, VISIBILITY_EXTENSION_SECONDS)
            except Exception as e:
                print(f"failed to extend message visibility: {e}")

    def __enter__(self):
        self._token = _heartbeat.set(self)
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._thread.join()
        _heartbeat.reset(self._token)


_heartbeat: ContextVar[Heartbeat | None] = ContextVar("heartbeat", default=None)


def beat(grace: float = 0) -> None:
    """Report progress on the current job (no-op outside a Heartbeat)."""
    hb = _heartbeat.get()
    if hb is not None:
        hb.beat(grace)


# --- Percent complete --------------------------------------------------------
# Written to jobs.progress so the frontend can draw a progress bar. Throttled
# so a long encode costs ~20 DB writes, not one per ffmpeg progress line.
PROGRESS_MIN_STEP = 5
PROGRESS_MIN_INTERVAL_SECONDS = 1.0


class Progress:
    """Writes the current job's percent complete to its DB row, throttled."""

    def __init__(self, job_id: str):
        self.job_id = job_id
        self._last_pct = 0
        self._last_write: float | None = None

    def report(self, pct: float) -> None:
        # Capped at 99: progress == 100 means "output ready" to the API
        # (GET /tasks/{id}/result), so only the final done-update may set it.
        pct = int(max(0, min(99, pct)))
        now = time.monotonic()
        if pct - self._last_pct < PROGRESS_MIN_STEP:
            return
        if self._last_write is not None and now - self._last_write < PROGRESS_MIN_INTERVAL_SECONDS:
            return
        self._last_write = now
        try:
            database.table("jobs").update({"progress": pct}).eq("id", self.job_id).execute()
        except Exception as e:
            # The bar is cosmetic; never fail a job over it.
            print(f"failed to update progress for job {self.job_id}: {e}")
            return
        self._last_pct = pct

    def __enter__(self):
        self._token = _progress.set(self)
        return self

    def __exit__(self, *exc):
        _progress.reset(self._token)


_progress: ContextVar[Progress | None] = ContextVar("progress", default=None)


def report_progress(pct: float) -> None:
    """Report the current job's percent complete (no-op outside a Progress)."""
    p = _progress.get()
    if p is not None:
        p.report(pct)


def probe_duration(path: str) -> float | None:
    """A media file's duration in seconds, or None if ffprobe can't tell.

    Only feeds the progress bar, so any failure just means no percentage.
    """
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return None
        duration = float(result.stdout.strip())
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return duration if math.isfinite(duration) and duration > 0 else None


def download(key: str, fd: int) -> None:
    """Stream an S3 object into an open mkstemp fd, beating per chunk."""
    with os.fdopen(fd, "wb") as dst:
        for chunk in s3.download_stream(key).iter_chunks():
            dst.write(chunk)
            beat()


def run_ffmpeg(args: list[str], duration: float | None = None) -> None:
    """Run ffmpeg, beating whenever its reported output position advances.

    With `duration` (seconds of output expected), each new position is also
    reported as a percentage for the progress bar.

    Raises CalledProcessError (with ffmpeg's stderr) on a non-zero exit so the
    run loop marks the job failed.
    """
    cmd = ["ffmpeg", "-y", "-nostats", "-loglevel", "error", "-progress", "pipe:1", *args]
    with tempfile.TemporaryFile() as err:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=err, text=True)
        last_position = None
        for line in proc.stdout:
            key, _, value = line.strip().partition("=")
            if key == "out_time_us" and value != last_position:
                last_position = value
                beat()
                # ffmpeg prints N/A (or a negative value) before the first frame.
                if duration is not None and duration > 0 and value.isdigit():
                    report_progress(int(value) / 1e6 / duration * 100)
        if proc.wait() != 0:
            err.seek(0)
            raise subprocess.CalledProcessError(proc.returncode, cmd, stderr=err.read())


def process_video_quality(job: VideoQualityJob, user_id: str) -> str:
    height = _HEIGHT[job.resolution]
    suffix = os.path.splitext(job.file_url)[1] or ".mp4"

    src_fd, src_path = tempfile.mkstemp(suffix=suffix)
    dst_fd, dst_path = tempfile.mkstemp(suffix=".mp4")
    os.close(dst_fd)
    try:
        download(job.file_url, src_fd)

        run_ffmpeg(
            [
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
            duration=probe_duration(src_path),
        )

        filename = os.path.basename(job.file_url)
        with open(dst_path, "rb") as out:
            return s3.upload_stream(
                user_id, filename, out, "video/mp4", prefix="processed"
            )
    finally:
        os.remove(src_path)
        os.remove(dst_path)


def process_image_deblur(job: DeblurJob, user_id: str) -> str:
    suffix = os.path.splitext(job.file_url)[1] or ".jpg"
    src_fd, src_path = tempfile.mkstemp(suffix=suffix)
    dst_fd, dst_path = tempfile.mkstemp(suffix=suffix)
    os.close(dst_fd)

    try:
        download(job.file_url, src_fd)
        image = cv2.imread(src_path)
        if image is None:
            raise RuntimeError("Failed to read uploaded image.")
        h, w = image.shape[:2]
        blob = cv2.dnn.blobFromImage(
            image,
            scalefactor=1 / 255.0,
            size=(w, h),
            mean=(0, 0, 0),
            swapRB=True,
            crop=False,
        )
        beat(grace=DEBLUR_GRACE_SECONDS)
        deblur_net.setInput(blob)
        output = deblur_net.forward()
        output = output.squeeze(0)
        output = np.transpose(output, (1, 2, 0))
        output = np.clip(output, 0, 1)
        output = (output * 255).astype(np.uint8)
        output = cv2.cvtColor(output, cv2.COLOR_RGB2BGR)

        cv2.imwrite(dst_path, output)
        content_type = (
            mimetypes.guess_type(job.file_url)[0] or "application/octet-stream"
        )
        filename = os.path.basename(job.file_url)
        with open(dst_path, "rb") as out:
            return s3.upload_stream(
                user_id, filename, out, content_type, prefix="processed"
            )
    finally:
        if os.path.exists(src_path):
            os.remove(src_path)
        if os.path.exists(dst_path):
            os.remove(dst_path)


def process_image_resize(job: ImageResizeJob, user_id: str) -> str:
    suffix = os.path.splitext(job.file_url)[1] or ".jpg"

    src_fd, src_path = tempfile.mkstemp(suffix=suffix)
    dst_fd, dst_path = tempfile.mkstemp(suffix=suffix)
    os.close(dst_fd)
    try:
        download(job.file_url, src_fd)

        run_ffmpeg(
            [
                "-i",
                src_path,
                "-vf",
                f"scale={job.width}:{job.height}",
                "-update",
                "1",
                dst_path,
            ]
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
        download(job.file_url, src_fd)

        # Image conversions are a single frame, so there's no progress to show.
        is_video = job.input_format in VIDEO_FORMATS
        run_ffmpeg(
            ["-i", src_path, dst_path],
            duration=probe_duration(src_path) if is_video else None,
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
        download(job.file_url, src_fd)

        # The output only covers the trimmed span (cut short if the video ends
        # before end_seconds), and ffmpeg reports positions within the output.
        probed = probe_duration(src_path)
        end = min(job.end_seconds, probed) if probed else job.end_seconds

        run_ffmpeg(
            [
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
            duration=end - job.start_seconds,
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


def process_extract_audio(job: ExtractAudioJob, user_id: str) -> str:
    codec_args, content_type = _AUDIO[job.format]
    suffix = os.path.splitext(job.file_url)[1] or ".mp4"

    src_fd, src_path = tempfile.mkstemp(suffix=suffix)
    dst_fd, dst_path = tempfile.mkstemp(suffix=f".{job.format}")
    os.close(dst_fd)
    try:
        download(job.file_url, src_fd)

        # -vn drops the picture; -map 0:a:0 takes the first audio track, so a
        # video with no sound fails here instead of producing an empty file.
        run_ffmpeg(
            ["-i", src_path, "-vn", "-map", "0:a:0", *codec_args, dst_path],
            duration=probe_duration(src_path),
        )

        # Name the output after the new format (clip.mp4 -> clip.mp3): the
        # frontend picks the preview and the download name by extension.
        stem = os.path.splitext(os.path.basename(job.file_url))[0]
        with open(dst_path, "rb") as out:
            return s3.upload_stream(
                user_id, f"{stem}.{job.format}", out, content_type, prefix="processed"
            )
    finally:
        os.remove(src_path)
        os.remove(dst_path)


def handle(job: JobRequest, user_id: str) -> str:
    match job:
        case TranscodeJob():
            raise NotImplementedError("transcode")
        case TrimJob():
            return process_trim(job, user_id)
        case ExtractAudioJob():
            return process_extract_audio(job, user_id)
        case VideoQualityJob():
            return process_video_quality(job, user_id)
        case ImageResizeJob():
            return process_image_resize(job, user_id)
        case DeblurJob():
            return process_image_deblur(job, user_id)
        case FormatConverterJob():
            return convert_format(job, user_id)
        case TranscribeJob():
            raise NotImplementedError("transcribe")
        case _:
            assert_never(job)


def run():
    print("worker started, polling for jobs...")
    while True:
        # One at a time: messages fetched in a batch would sit unextended (and
        # time out) while the ones ahead of them are processed.
        for msg in queue.receive(max_messages=1):
            body = json.loads(msg["Body"])
            job_id = body["job_id"]
            user_id = body["user_id"]
            try:
                # Reset progress too, so a retried job doesn't start half full.
                database.table("jobs").update(
                    {"status": "processing", "progress": 0}
                ).eq("id", job_id).execute()
                job = job_adapter.validate_python(body)
                with Heartbeat(msg["ReceiptHandle"]), Progress(job_id):
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
