from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from db.client import database
from jobs import JobRequest  # <-- the canonical type
from job_queue import JobQueue

router = APIRouter()


queue = JobQueue()


@router.post("/tasks")
async def create_task(job: JobRequest):
    response = (
        database.table("jobs")
        .insert(
            {
                "job_type": job.type,  # <-- map: model.type    -> column job_type
                "input_file_url": job.file_url,  # <-- map: model.file_url -> column input_file_url
            }
        )
        .execute()
    )
    job_id = response.data[0]["id"]

    queue.send({"job_id": job_id, **job.model_dump()})  # full typed payload + id
    return {"message": "Task created successfully", "task_id": job_id}


@router.get("/tasks")
async def get_all_tasks():
    response = database.table("jobs").select("*").execute()
    return {"tasks": response.data}


@router.get("/tasks/{task_id}")
async def get_task(task_id: str):
    response = database.table("jobs").select("*").eq("id", task_id).execute()
    if not response.data:
        raise HTTPException(status_code=404, detail="Task not found")
    else:
        return {"task": response.data[0]}


@router.get("/tasks/{task_id}/result")
async def get_task_result(task_id: str):
    response = (
        database.table("jobs").select("output_file_url").eq("id", task_id).execute()
    )
    if not response.data or not response.data[0]["output_file_url"]:
        raise HTTPException(status_code=404, detail="File not ready yet")
    else:
        return {
            "output_file_url": response.data[0]["output_file_url"]
        }  # downloadable link to output file


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str):
    response = database.table("jobs").delete().eq("id", task_id).execute()
    if not response.data:
        raise HTTPException(status_code=404, detail="Task not found")
    else:
        return {"message": "Task deleted successfully"}

