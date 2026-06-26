from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from pydantic import BaseModel
from db.client import database
from jobs import JobRequest  # <-- the canonical type
from job_queue import JobQueue
from auth import get_current_user, User
from s3_client import S3Client

router = APIRouter()


queue = JobQueue()
s3 = S3Client()

@router.post("/tasks")
async def create_task(job: JobRequest, current_user: User = Depends(get_current_user)):
    user_id = current_user.id
    response = (
        database.table("jobs")
        .insert(
            {
                "job_type": job.type,  # <-- map: model.type    -> column job_type
                "input_key": job.file_url,  # <-- map: model.file_url -> column input_key, file_url should be the s3 key to original file
                "user_id" : user_id
            }
        )
        .execute()
    )
    job_id = response.data[0]["id"]

    queue.send({"job_id": job_id, **job.model_dump()})  # full typed payload + id
    return {"message": "Task created successfully", "task_id": job_id}

@router.post("/upload")
async def upload_file(file: UploadFile = File(...), current_user: User = Depends(get_current_user)):
    user_id = current_user.id
    file_key = s3.upload_stream(file.filename, file.file, file.content_type)
    return {"file_key": file_key}

#user uploads file -> call /upload to upload file to s3 and get key -> call /tasks with key to finish processing and upload info to db

@router.get("/tasks")
async def get_all_tasks(current_user : User = Depends(get_current_user)):
    response = database.table("jobs").select("*").eq("user_id", current_user.id).execute()
    return {"tasks": response.data}


@router.get("/tasks/{task_id}")
async def get_task(task_id: str, current_user : User = Depends(get_current_user)):
    response = database.table("jobs").select("*").eq("id", task_id).eq("user_id", current_user.id).execute()
    if not response.data:
        raise HTTPException(status_code=404, detail="Task not found")
    else:
        return {"task": response.data[0]}


@router.get("/tasks/{task_id}/result")
async def get_task_result(task_id: str, current_user : User = Depends(get_current_user)):
    response = (
        database.table("jobs")
        .select("output_key")
        .eq("id", task_id)
        .eq("user_id", current_user.id)
        .eq("progress", 100)
        .execute()
    )

    if not response.data or not response.data[0]:
        raise HTTPException(status_code=404, detail="File not ready yet")
    else:
        url = s3.get_output_url(response.data[0]["output_key"])
        return {"output_file_url": url}


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str, current_user : User = Depends(get_current_user)):
    response = database.table("jobs").delete().eq("id", task_id).eq("user_id", current_user.id).execute()
    if not response.data:
        raise HTTPException(status_code=404, detail="Task not found")
    else:
        job = response.data[0]
        s3.delete_object(job["input_key"])
        if job["output_key"]:
            s3.delete_object(job["output_key"])
        return {"message": "Task deleted successfully"}

