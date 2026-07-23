"""Worker processing logic — process_video_quality() and handle() dispatch.

The S3 client and the ffmpeg subprocess are mocked so no bytes leave the box:
we assert on the ffmpeg command that *would* run and the S3 upload target.
"""
import subprocess as sp

import pytest

import worker
from jobs import VideoQualityJob, ImageResizeJob


class FakeBody:
    """Stand-in for boto3's StreamingBody."""

    def iter_chunks(self):
        yield b"fake-video-bytes"


@pytest.fixture
def captured(monkeypatch):
    """Patch worker's S3 + subprocess boundaries; return a dict of captured calls."""
    calls = {}

    monkeypatch.setattr(worker.s3, "download_stream", lambda key: FakeBody())

    def fake_run(cmd, **kwargs):
        calls["cmd"] = cmd
        calls["run_kwargs"] = kwargs
        return sp.CompletedProcess(cmd, 0, b"", b"")

    monkeypatch.setattr(worker.subprocess, "run", fake_run)

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
    assert cmd[0] == "ffmpeg"
    assert "scale=-2:720" in cmd
    # errors should surface (check=True) so the run loop marks the job failed
    assert captured["run_kwargs"].get("check") is True


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
    assert cmd[0] == "ffmpeg"
    assert "scale=400:300" in cmd
    # errors should surface (check=True) so the run loop marks the job failed
    assert captured["run_kwargs"].get("check") is True


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
