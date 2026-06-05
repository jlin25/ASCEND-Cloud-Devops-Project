from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from db.client import database

router = APIRouter()

class TaskRequest(BaseModel):
    input_file_url: str
    job_type: str

@router.post("/tasks")
async def create_task(task_request: TaskRequest):
    response = database.table("jobs").insert({
        "input_file_url": task_request.input_file_url,
        "job_type": task_request.job_type
    }).execute()

    #retrieve userid from authentication and update
    #add actual file to storage like AWS S3?
    return {"message": "Task created successfully", "task_id": response.data[0]["id"]}

@router.get("/tasks")
async def get_all_tasks():
    response = database.table("jobs").select("*").execute()
    return {"tasks": response.data}

@router.get("/tasks/{task_id}")
async def get_task(task_id : str):
    response = database.table("jobs").select("*").eq("id", task_id).execute()
    if not response.data:
        raise HTTPException(status_code=404, detail="Task not found")
    else:
        return {"task": response.data[0]}

@router.get("/tasks/{task_id}/result")
async def get_task_result(task_id : str):
    response = database.table("jobs").select("output_file_url").eq("id", task_id).execute()
    if not response.data or not response.data[0]["output_file_url"]:
        raise HTTPException(status_code=404, detail="File not ready yet")
    else:
        return {"output_file_url": response.data[0]["output_file_url"]} #downloadable link to output file

@router.delete("/tasks/{task_id}")
async def delete_task(task_id : str):
    response = database.table("jobs").delete().eq("id", task_id).execute()
    if not response.data :
        raise HTTPException(status_code=404, detail="Task not found")
    else:
        return {"message": "Task deleted successfully"}