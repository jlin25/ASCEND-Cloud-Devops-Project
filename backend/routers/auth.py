import os
import bcrypt
from jose import jwt
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from db.client import database

router = APIRouter()

<<<<<<< HEAD
=======
SECRET_KEY = os.getenv("SECRET_KEY", "fallback-secret-key")
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24

>>>>>>> 11b10462b48890f9e96bf4460780bc54fd1cbc48

class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str


<<<<<<< HEAD
@router.post("auth/login")
async def login(request: LoginRequest):
    response = (
        database.table("users").select("*").eq("username", request.username).execute()
    )
    if not response.data:
        raise HTTPException(status_code=401, detail="Invalid username or password")
=======
def create_token(user_id: str, username: str) -> str:
    payload = {
        "sub": user_id,
        "username": username,
        "exp": datetime.utcnow() + timedelta(hours=TOKEN_EXPIRE_HOURS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


@router.post("/auth/register")
async def register(request: RegisterRequest):
    # Check if username already taken
    existing = database.table("users").select("id").eq("username", request.username).execute()
    if existing.data:
        raise HTTPException(status_code=400, detail="Username already taken.")

    # Hash the password — never store the raw password
    password_hash = bcrypt.hashpw(request.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    # Insert new user into Supabase
    result = database.table("users").insert({
        "username": request.username,
        "password_hash": password_hash,
    }).execute()

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create account.")

    new_user = result.data[0]
    token = create_token(new_user["id"], new_user["username"])

    return {"token": token, "username": new_user["username"]}


@router.post("/auth/login")
async def login(request: LoginRequest):
    # Look up user by username
    response = database.table("users").select("*").eq("username", request.username).execute()
    if not response.data:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
>>>>>>> 11b10462b48890f9e96bf4460780bc54fd1cbc48

    user = response.data[0]

<<<<<<< HEAD

@router.post("auth/register")
async def register(request: RegisterRequest):
    existing = (
        database.table("users").select("*").eq("username", request.username).execute()
    )
    if existing.data:
        raise HTTPException(status_code=400, detail="Username already exists")
    # When password hashing is implemented, hash the password then store in database + other security logic
    return {"message": "Registration successful"}


@router.post("auth/logout")
async def logout():
    # Implement session token invalidation logic when authentication is implemented
    return {"message": "Logout successful"}

=======
    # Check submitted password against stored hash
    password_matches = bcrypt.checkpw(
        request.password.encode("utf-8"),
        user["password_hash"].encode("utf-8")
    )
    if not password_matches:
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    token = create_token(user["id"], user["username"])

    return {"token": token, "username": user["username"]}


@router.post("/auth/logout")
async def logout():
    # JWT tokens are stateless — logout is handled by the frontend deleting the token
    return {"message": "Logged out successfully."}
>>>>>>> 11b10462b48890f9e96bf4460780bc54fd1cbc48
