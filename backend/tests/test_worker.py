"""Worker processing logic — the process_* functions, handle() dispatch, and
the visibility heartbeat.

The S3 client and ffmpeg are mocked so no bytes leave the box: we assert on
the ffmpeg arguments that *would* run and the S3 upload target.
"""
import subprocess as sp
import time

import cv2
import numpy as np
import pytest

import worker
from jobs import (
    DeblurJob,
    ExtractAudioJob,
    FormatConverterJob,
    ImageResizeJob,
    TranscodeJob,
    TrimJob,
    VideoQualityJob,
)


class FakeBody:
    """Stand-in for boto3's StreamingBody."""

    def iter_chunks(self):
        yield b"fake-video-bytes"


@pytest.fixture
def captured(monkeypatch):
    """Patch worker's S3 + subprocess boundaries; return a dict of captured calls."""
    calls = {}

    monkeypatch.setattr(worker.s3, "download_stream", lambda key: FakeBody())

    def fake_run_ffmpeg(args, duration=None):
        calls["cmd"] = args
        calls["duration"] = duration

    monkeypatch.setattr(worker, "run_ffmpeg", fake_run_ffmpeg)
    # Every downloaded "video" is 10 seconds long.
    monkeypatch.setattr(worker, "probe_duration", lambda path: 10.0)

    def fake_upload(user_id, filename, fileobj, content_type, prefix="uploads"):
        calls["upload"] = {
            "user_id": user_id,
            "filename": filename,
            "content_type": content_type,
            "prefix": prefix,
        }
        return f"{prefix}/{user_id}/{filename}"

    monkeypatch.setattr(worker.s3, "upload_stream", fake_upload)
    return calls


def test_process_video_quality_uploads_to_processed_prefix(captured):
    job = VideoQualityJob(
        type="video_quality", file_url="uploads/u1/abc.mp4", resolution="1080p"
    )
    out = worker.process_video_quality(job, "u1")

    assert out == "processed/u1/abc.mp4"
    assert captured["upload"]["user_id"] == "u1"
    assert captured["upload"]["prefix"] == "processed"
    assert captured["upload"]["content_type"] == "video/mp4"
    assert captured["upload"]["filename"] == "abc.mp4"


def test_process_video_quality_invokes_ffmpeg(captured):
    job = VideoQualityJob(type="video_quality", file_url="uploads/u1/a.mp4", resolution="720p")
    worker.process_video_quality(job, "u1")

    cmd = captured["cmd"]
    assert cmd[:2] == ["-i", cmd[1]]
    assert "scale=-2:720" in cmd


@pytest.mark.parametrize("res,height", [("720p", 720), ("1080p", 1080), ("4k", 2160)])
def test_resolution_maps_to_ffmpeg_height(captured, res, height):
    job = VideoQualityJob(type="video_quality", file_url="uploads/u1/a.mp4", resolution=res)
    worker.process_video_quality(job, "u1")
    assert f"scale=-2:{height}" in captured["cmd"]


def test_handle_dispatches_video_quality(monkeypatch):
    seen = {}

    def fake_process(job, user_id):
        seen["args"] = (job, user_id)
        return "processed/u1/out.mp4"

    monkeypatch.setattr(worker, "process_video_quality", fake_process)
    job = VideoQualityJob(type="video_quality", file_url="k", resolution="720p")
    result = worker.handle(job, "u9")

    assert result == "processed/u1/out.mp4"
    assert seen["args"][1] == "u9"


def test_process_image_resize_uploads_to_processed_prefix(captured):
    job = ImageResizeJob(
        type="image_resize", file_url="uploads/u1/photo.png", width=800, height=600
    )
    out = worker.process_image_resize(job, "u1")

    assert out == "processed/u1/photo.png"
    assert captured["upload"]["user_id"] == "u1"
    assert captured["upload"]["prefix"] == "processed"
    assert captured["upload"]["filename"] == "photo.png"


def test_process_image_resize_preserves_content_type(captured):
    job = ImageResizeJob(
        type="image_resize", file_url="uploads/u1/photo.png", width=800, height=600
    )
    worker.process_image_resize(job, "u1")

    # content-type should be derived from the original file's extension (.png),
    # not hardcoded to jpeg
    assert captured["upload"]["content_type"] == "image/png"


def test_process_image_resize_invokes_ffmpeg(captured):
    job = ImageResizeJob(
        type="image_resize", file_url="uploads/u1/a.jpg", width=400, height=300
    )
    worker.process_image_resize(job, "u1")

    cmd = captured["cmd"]
    assert cmd[0] == "-i"
    assert "scale=400:300" in cmd


@pytest.mark.parametrize(
    "width,height", [(100, 100), (1920, 1080), (50, 200)]
)
def test_image_resize_dimensions_land_in_ffmpeg_command(captured, width, height):
    job = ImageResizeJob(
        type="image_resize", file_url="uploads/u1/a.png", width=width, height=height
    )
    worker.process_image_resize(job, "u1")
    assert f"scale={width}:{height}" in captured["cmd"]


def test_handle_dispatches_image_resize(monkeypatch):
    seen = {}

    def fake_process(job, user_id):
        seen["args"] = (job, user_id)
        return "processed/u1/out.png"

    monkeypatch.setattr(worker, "process_image_resize", fake_process)
    job = ImageResizeJob(type="image_resize", file_url="k", width=100, height=100)
    result = worker.handle(job, "u9")

    assert result == "processed/u1/out.png"
    assert seen["args"][1] == "u9"


def test_process_image_deblur_uploads_result(captured, monkeypatch):
    png = cv2.imencode(".png", np.zeros((4, 6, 3), np.uint8))[1].tobytes()

    class PngBody:
        def iter_chunks(self):
            yield png

    class FakeNet:
        def setInput(self, blob):
            self.shape = blob.shape

        def forward(self):
            return np.zeros(self.shape, np.float32)

    monkeypatch.setattr(worker.s3, "download_stream", lambda key: PngBody())
    monkeypatch.setattr(worker, "deblur_net", FakeNet())
    job = DeblurJob(type="deblur", file_url="uploads/u1/blurry.png")
    out = worker.process_image_deblur(job, "u1")

    assert out == "processed/u1/blurry.png"
    assert captured["upload"]["content_type"] == "image/png"


def test_process_extract_audio_names_output_after_format(captured):
    job = ExtractAudioJob(type="extract_audio", file_url="uploads/u1/abc.mp4", format="mp3")
    out = worker.process_extract_audio(job, "u1")

    # The output takes the new format's extension, not the video's.
    assert out == "processed/u1/abc.mp3"
    assert captured["upload"]["filename"] == "abc.mp3"
    assert captured["upload"]["prefix"] == "processed"
    assert captured["upload"]["content_type"] == "audio/mpeg"


@pytest.mark.parametrize(
    "fmt,codec,content_type",
    [("mp3", "libmp3lame", "audio/mpeg"), ("wav", "pcm_s16le", "audio/wav"), ("aac", "aac", "audio/aac")],
)
def test_process_extract_audio_invokes_ffmpeg(captured, fmt, codec, content_type):
    job = ExtractAudioJob(type="extract_audio", file_url="uploads/u1/clip.mov", format=fmt)
    worker.process_extract_audio(job, "u1")

    cmd = captured["cmd"]
    assert cmd[0] == "-i"
    assert "-vn" in cmd
    # First audio track only, so a silent video fails instead of producing nothing.
    assert cmd[cmd.index("-map") + 1] == "0:a:0"
    assert cmd[cmd.index("-c:a") + 1] == codec
    assert cmd[-1].endswith(f".{fmt}")
    assert captured["upload"]["content_type"] == content_type
    # The audio runs as long as the source video.
    assert captured["duration"] == 10.0


def test_handle_dispatches_extract_audio(monkeypatch):
    seen = {}

    def fake_process(job, user_id):
        seen["args"] = (job, user_id)
        return "processed/u1/out.mp3"

    monkeypatch.setattr(worker, "process_extract_audio", fake_process)
    job = ExtractAudioJob(type="extract_audio", file_url="k", format="mp3")
    result = worker.handle(job, "u9")

    assert result == "processed/u1/out.mp3"
    assert seen["args"][1] == "u9"


def test_handle_rejects_unimplemented_job_types():
    job = TranscodeJob(type="transcode", file_url="k", format="mp4", resolution="720p")
    with pytest.raises(NotImplementedError):
        worker.handle(job, "u1")


# --- run_ffmpeg -------------------------------------------------------------
class FakePopen:
    """Stand-in for subprocess.Popen emitting ffmpeg `-progress` output."""

    lines = []
    returncode = 0

    def __init__(self, cmd, **kwargs):
        FakePopen.cmd = cmd
        self.stdout = iter(self.lines)

    def wait(self):
        return self.returncode


@pytest.fixture
def fake_popen(monkeypatch):
    monkeypatch.setattr(worker.subprocess, "Popen", FakePopen)
    beats = []
    monkeypatch.setattr(worker, "beat", lambda grace=0: beats.append(grace))
    return beats


def test_run_ffmpeg_beats_only_when_position_advances(fake_popen, monkeypatch):
    monkeypatch.setattr(FakePopen, "returncode", 0)
    monkeypatch.setattr(
        FakePopen,
        "lines",
        ["out_time_us=0\n", "fps=30\n", "out_time_us=0\n", "out_time_us=500000\n", "progress=end\n"],
    )
    worker.run_ffmpeg(["-i", "in.mp4", "out.mp4"])

    assert len(fake_popen) == 2
    assert FakePopen.cmd[0] == "ffmpeg"
    assert FakePopen.cmd[-3:] == ["-i", "in.mp4", "out.mp4"]
    assert "-progress" in FakePopen.cmd


def test_run_ffmpeg_raises_on_failure(fake_popen, monkeypatch):
    monkeypatch.setattr(FakePopen, "lines", [])
    monkeypatch.setattr(FakePopen, "returncode", 1)
    with pytest.raises(sp.CalledProcessError):
        worker.run_ffmpeg(["-i", "missing.mp4", "out.mp4"])


def test_run_ffmpeg_reports_percent_of_duration(fake_popen, monkeypatch):
    reported = []
    monkeypatch.setattr(worker, "report_progress", reported.append)
    monkeypatch.setattr(FakePopen, "returncode", 0)
    monkeypatch.setattr(
        FakePopen,
        "lines",
        ["out_time_us=N/A\n", "out_time_us=0\n", "out_time_us=2500000\n", "out_time_us=5000000\n"],
    )
    worker.run_ffmpeg(["-i", "in.mp4", "out.mp4"], duration=10)

    assert reported == [0, 25, 50]


def test_run_ffmpeg_without_duration_reports_nothing(fake_popen, monkeypatch):
    reported = []
    monkeypatch.setattr(worker, "report_progress", reported.append)
    monkeypatch.setattr(FakePopen, "returncode", 0)
    monkeypatch.setattr(FakePopen, "lines", ["out_time_us=2500000\n"])
    worker.run_ffmpeg(["-i", "in.png", "out.png"])

    assert reported == []


# --- Progress ---------------------------------------------------------------
class FakeJobsTable:
    def __init__(self, writes):
        self.writes = writes

    def update(self, data):
        self.writes.append(data["progress"])
        return self

    def eq(self, *args):
        return self

    def execute(self):
        return None


@pytest.fixture
def progress_writes(monkeypatch):
    """Capture progress values written to the jobs table; no write throttle."""
    writes = []

    class FakeDb:
        def table(self, name):
            return FakeJobsTable(writes)

    monkeypatch.setattr(worker, "database", FakeDb())
    monkeypatch.setattr(worker, "PROGRESS_MIN_INTERVAL_SECONDS", 0)
    return writes


def test_report_progress_outside_a_job_is_noop(progress_writes):
    worker.report_progress(50)
    assert progress_writes == []


def test_progress_writes_in_steps_and_never_reaches_100(progress_writes):
    with worker.Progress("job-1"):
        for pct in [0, 3, 5, 7, 12, 50, 99.9, 120]:
            worker.report_progress(pct)

    # 100 is reserved for "done": the result endpoint treats it as output-ready.
    assert progress_writes == [5, 12, 50, 99]


def test_progress_waits_between_writes(progress_writes, monkeypatch):
    monkeypatch.setattr(worker, "PROGRESS_MIN_INTERVAL_SECONDS", 60)
    with worker.Progress("job-1"):
        worker.report_progress(10)
        worker.report_progress(50)

    assert progress_writes == [10]


def test_progress_write_failure_does_not_fail_the_job(monkeypatch):
    class BrokenDb:
        def table(self, name):
            raise RuntimeError("db down")

    monkeypatch.setattr(worker, "database", BrokenDb())
    with worker.Progress("job-1"):
        worker.report_progress(50)


# --- probe_duration ---------------------------------------------------------
@pytest.mark.parametrize(
    "stdout,returncode,expected",
    [("12.34\n", 0, 12.34), ("N/A\n", 0, None), ("", 1, None), ("0.000000\n", 0, None)],
)
def test_probe_duration(monkeypatch, stdout, returncode, expected):
    monkeypatch.setattr(
        worker.subprocess,
        "run",
        lambda cmd, **kw: sp.CompletedProcess(cmd, returncode, stdout=stdout, stderr=""),
    )
    assert worker.probe_duration("in.mp4") == expected


def test_probe_duration_without_ffprobe(monkeypatch):
    def missing(cmd, **kw):
        raise FileNotFoundError("ffprobe")

    monkeypatch.setattr(worker.subprocess, "run", missing)
    assert worker.probe_duration("in.mp4") is None


# --- Which handlers report a duration ---------------------------------------
def test_video_quality_passes_probed_duration(captured):
    job = VideoQualityJob(type="video_quality", file_url="uploads/u1/a.mp4", resolution="720p")
    worker.process_video_quality(job, "u1")
    assert captured["duration"] == 10.0


def test_trim_duration_is_the_trimmed_span(captured):
    job = TrimJob(type="trim", file_url="uploads/u1/a.mp4", start_seconds=2, end_seconds=5)
    worker.process_trim(job, "u1")
    assert captured["duration"] == 3


def test_trim_duration_stops_at_end_of_video(captured):
    # The fake video is 10s long, so a 4s..60s trim only produces 6s.
    job = TrimJob(type="trim", file_url="uploads/u1/a.mp4", start_seconds=4, end_seconds=60)
    worker.process_trim(job, "u1")
    assert captured["duration"] == 6


def test_video_format_conversion_passes_duration(captured):
    job = FormatConverterJob(
        type="format_converter", file_url="uploads/u1/a.mp4", input_format="mp4", output_format="webm"
    )
    worker.convert_format(job, "u1")
    assert captured["duration"] == 10.0


def test_image_jobs_pass_no_duration(captured):
    worker.process_image_resize(
        ImageResizeJob(type="image_resize", file_url="uploads/u1/a.png", width=10, height=10), "u1"
    )
    assert captured["duration"] is None

    worker.convert_format(
        FormatConverterJob(
            type="format_converter", file_url="uploads/u1/a.png", input_format="png", output_format="jpg"
        ),
        "u1",
    )
    assert captured["duration"] is None


# --- Heartbeat --------------------------------------------------------------
@pytest.fixture
def extensions(monkeypatch):
    calls = []
    monkeypatch.setattr(worker, "HEARTBEAT_INTERVAL_SECONDS", 0.02)
    monkeypatch.setattr(worker, "STALL_TIMEOUT_SECONDS", 0.1)
    monkeypatch.setattr(worker.queue, "extend", lambda handle, seconds: calls.append(handle))
    return calls


def test_heartbeat_extends_while_progressing(extensions):
    with worker.Heartbeat("rh-1"):
        for _ in range(10):
            worker.beat()
            time.sleep(0.03)
    assert len(extensions) >= 5
    assert set(extensions) == {"rh-1"}


def test_heartbeat_stops_extending_when_stalled(extensions):
    with worker.Heartbeat("rh-1") as hb:
        time.sleep(0.3)
        assert not hb.progressing()
    # Only the ticks inside the stall window extended; then it gave up.
    assert len(extensions) <= 6


def test_heartbeat_grace_covers_unobservable_step(extensions):
    with worker.Heartbeat("rh-1") as hb:
        worker.beat(grace=0.4)
        time.sleep(0.25)
        assert hb.progressing()


def test_beat_outside_heartbeat_is_noop():
    worker.beat()
