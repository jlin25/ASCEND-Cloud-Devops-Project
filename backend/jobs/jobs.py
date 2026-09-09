from pydantic import BaseModel, Field, TypeAdapter, model_validator
from typing import Literal, Annotated

VIDEO_FORMATS = {"mp4", "mov", "avi", "webm"}
IMAGE_FORMATS = {"jpg", "png", "webp"}


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


class VideoQualityJob(BaseModel):
    type: Literal["video_quality"]
    file_url: str
    resolution: Literal["720p", "1080p", "4k"]


class ImageResizeJob(BaseModel):
    type: Literal["image_resize"]
    file_url: str
    width: int
    height: int


class FormatConverterJob(BaseModel):
    type: Literal["format_converter"]
    file_url: str
    input_format: Literal[
        "mp4", "mov", "avi", "webm", "jpg", "png", "webp"
    ]
    output_format: Literal[
        "mp4", "mov", "avi", "webm", "jpg", "png", "webp"
    ]

    @model_validator(mode="after")
    def validate_formats(self):
        input_is_video = self.input_format in VIDEO_FORMATS
        output_is_video = self.output_format in VIDEO_FORMATS

        if input_is_video != output_is_video:
            raise ValueError(
                f"Cannot convert between video and image formats: "
                f"{self.input_format} -> {self.output_format}"
            )

        if self.input_format == self.output_format:
            raise ValueError(
                f"Input and output formats are the same: "
                f"{self.input_format}"
            )

        return self


class TranscribeJob(BaseModel):
    type: Literal["transcribe"]
    file_url: str


JobRequest = Annotated[
    TranscodeJob
    | TrimJob
    | ExtractAudioJob
    | VideoQualityJob
    | ImageResizeJob
    | FormatConverterJob
    | TranscribeJob,
    Field(discriminator="type"),
]

job_adapter = TypeAdapter(JobRequest)