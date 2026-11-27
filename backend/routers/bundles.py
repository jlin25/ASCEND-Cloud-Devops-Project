#Download a set of results as one ZIP. A bundle is an internal job, it is not available as a job the user can select.

import io
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from db.client import database
from job_queue import JobQueue
from routers.auth import User, get_current_user
from routers.tasks import INTERNAL_JOB_TYPE
from s3_client import S3Client, original_name

router = APIRouter()

queue = JobQueue()
s3 = S3Client()

# Maximum number of task IDs to look up in one query
LOOKUP_CHUNK = 100

DOWNLOAD_LINK_SECONDS = 3600


class BundleRequest(BaseModel):
    task_ids: list[str] = Field(min_length=1)


def _delete_files(row: dict) -> None:
    #Remove a bundle's manifest and ZIP
    for key in (row.get("input_key"), row.get("output_key")):
        if not key:
            continue
        try:
            s3.delete_object(key)
        except Exception as e:
            print(f"failed to delete bundle file {key}: {e}")


def _cleanup_previous(user_id: str) -> None:
    # Keep at most one stored ZIP per user: drop their finished/failed bundles
    old = (
        database.table("jobs")
        .select("id, input_key, output_key")
        .eq("user_id", user_id)
        .eq("job_type", INTERNAL_JOB_TYPE)
        .in_("status", ["done", "failed"])
        .execute()
    )
    if not old.data:
        return
    database.table("jobs").delete().in_("id", [r["id"] for r in old.data]).execute()
    for row in old.data:
        _delete_files(row)


@router.post("/bundles")
async def create_bundle(req: BundleRequest, current_user: User = Depends(get_current_user)):
    user_id = current_user.id
    ids = list(dict.fromkeys(req.task_ids))  # drop duplicates, keep order

    keys: list[str] = []
    for i in range(0, len(ids), LOOKUP_CHUNK):
        response = (
            database.table("jobs")
            .select("output_key")
            .in_("id", ids[i : i + LOOKUP_CHUNK])
            .eq("user_id", user_id)
            .eq("status", "done")
            .neq("job_type", INTERNAL_JOB_TYPE)
            .execute()
        )
        keys += [row["output_key"] for row in response.data if row.get("output_key")]

    if not keys:
        raise HTTPException(status_code=400, detail="None of these jobs have results yet")

    _cleanup_previous(user_id)

    manifest = io.BytesIO(json.dumps({"files": keys}).encode())
    manifest_key = s3.upload_stream(
        user_id, f"results-{len(keys)}-files.json", manifest, "application/json", prefix="bundles"
    )

    response = (
        database.table("jobs")
        .insert({"job_type": INTERNAL_JOB_TYPE, "input_key": manifest_key, "user_id": user_id})
        .execute()
    )
    bundle_id = response.data[0]["id"]

    queue.send({"job_id": bundle_id, "user_id": user_id, "type": INTERNAL_JOB_TYPE, "file_url": manifest_key})
    return {"bundle_id": bundle_id}


@router.get("/bundles/{bundle_id}")
async def get_bundle(bundle_id: str, current_user: User = Depends(get_current_user)):
    response = (
        database.table("jobs")
        .select("status, progress, output_key")
        .eq("id", bundle_id)
        .eq("user_id", current_user.id)
        .eq("job_type", INTERNAL_JOB_TYPE)
        .execute()
    )
    if not response.data:
        raise HTTPException(status_code=404, detail="Download not found")
    row = response.data[0]
    ready = row["status"] == "done" and row["output_key"]
    return {
        "status": row["status"],
        "progress": row["progress"],
        "download_url": (
            s3.get_output_url(
                row["output_key"],
                expires_in=DOWNLOAD_LINK_SECONDS,
                download_name=original_name(row["output_key"]),
            )
            if ready
            else None
        ),
    }


@router.delete("/bundles/{bundle_id}")
async def delete_bundle(bundle_id: str, current_user: User = Depends(get_current_user)):
    response = (
        database.table("jobs")
        .delete()
        .eq("id", bundle_id)
        .eq("user_id", current_user.id)
        .eq("job_type", INTERNAL_JOB_TYPE)
        .execute()
    )
    if not response.data:
        raise HTTPException(status_code=404, detail="Download not found")
    _delete_files(response.data[0])
    return {"message": "Download deleted"}
