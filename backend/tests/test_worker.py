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
from jobs import DeblurJob, ImageResizeJob, TranscodeJob, VideoQualityJob


class FakeBody:
    """Stand-in for boto3's StreamingBody."""

    def iter_chunks(self):
        yield b"fake-video-bytes"


@pytest.fixture
def captured(monkeypatch):
    """Patch worker's S3 + subprocess boundaries; return a dict of captured calls."""
    calls = {}

    monkeypatch.setattr(worker.s3, "download_stream", lambda key: FakeBody())

    def fake_run_ffmpeg(args):
        calls["cmd"] = args

    monkeypatch.setattr(worker, "run_ffmpeg", fake_run_ffmpeg)

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
