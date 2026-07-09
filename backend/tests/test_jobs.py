"""Job model validation — the discriminated union in jobs/jobs.py.

Pure, no mocks: exercises pydantic parsing and the `type` discriminator.
"""
import pytest
from pydantic import ValidationError

from jobs import (
    job_adapter,
    TranscodeJob,
    TrimJob,
    ExtractAudioJob,
    VideoQualityJob,
)


def test_video_quality_valid():
    job = job_adapter.validate_python(
        {"type": "video_quality", "file_url": "uploads/u1/abc.mp4", "resolution": "1080p"}
    )
    assert isinstance(job, VideoQualityJob)
    assert job.file_url == "uploads/u1/abc.mp4"
    assert job.resolution == "1080p"


@pytest.mark.parametrize("res", ["720p", "1080p", "4k"])
def test_video_quality_all_resolutions(res):
    job = job_adapter.validate_python(
        {"type": "video_quality", "file_url": "k", "resolution": res}
    )
    assert job.resolution == res


def test_video_quality_bad_resolution_rejected():
    with pytest.raises(ValidationError):
        job_adapter.validate_python(
            {"type": "video_quality", "file_url": "k", "resolution": "480p"}
        )


def test_video_quality_missing_resolution_rejected():
    with pytest.raises(ValidationError):
        job_adapter.validate_python({"type": "video_quality", "file_url": "k"})


def test_unknown_type_rejected():
    with pytest.raises(ValidationError):
        job_adapter.validate_python({"type": "sharpen", "file_url": "k"})


def test_discriminator_dispatches_each_type():
    assert isinstance(
        job_adapter.validate_python(
            {"type": "transcode", "file_url": "k", "format": "mp4", "resolution": "720p"}
        ),
        TranscodeJob,
    )
    assert isinstance(
        job_adapter.validate_python(
            {"type": "trim", "file_url": "k", "start_seconds": 0, "end_seconds": 5}
        ),
        TrimJob,
    )
    assert isinstance(
        job_adapter.validate_python(
            {"type": "extract_audio", "file_url": "k", "format": "mp3"}
        ),
        ExtractAudioJob,
    )
