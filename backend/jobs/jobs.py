from pydantic import BaseModel, Field, TypeAdapter
from typing import Literal, Annotated


class TranscodeJob(BaseModel):
    type: Literal["transcode"]
    file_url: str
    format: Literal["mp4", "webm", "mov"]
    resolution: Literal["720p", "1080p", "4k"]


class ExtractAudioJob(BaseModel):
    type: Literal["extract_audio"]
    file_url: str
    format: Literal["mp3", "wav", "aac"]


class TrimJob(BaseModel):
    type: Literal["trim"]
    file_url: str
    start_seconds: float
    end_seconds: float


type JobRequest = Annotated[
    TranscodeJob | TrimJob | ExtractAudioJob,
    Field(discriminator="type"),
]
job_adapter = TypeAdapter(JobRequest)
