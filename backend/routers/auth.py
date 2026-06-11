from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from db.client import database

router = APIRouter()

class LoginRequest(BaseModel):
    username: str
    password: str

class RegisterRequest(BaseModel):
    username: str
    password: str

@router.post("auth/login")
async def login(request : LoginRequest):
    response = database.table("users").select("*").eq("username", request.username).execute()
    if not response.data:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    
    user = response.data[0]
    # When password hashing is implemented, add password verification logic, return user session token etc.
    return {"message": "Login successful"}

@router.post("auth/register")
async def register(request : RegisterRequest):
    existing = database.table("users").select("*").eq("username", request.username).execute()
    if existing.data:
        raise HTTPException(status_code=400, detail="Username already exists")
    # When password hashing is implemented, hash the password then store in database + other security logic
    return {"message": "Registration successful"}

@router.post("auth/logout")
async def logout():
    # Implement session token invalidation logic when authentication is implemented
    return {"message": "Logout successful"}