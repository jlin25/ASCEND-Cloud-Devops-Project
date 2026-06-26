import os
import bcrypt
from jose import jwt, JWTError
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from db.client import database

router = APIRouter()

SECRET_KEY = os.getenv("SECRET_KEY", "fallback-secret-key")
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24

security = HTTPBearer()

class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str

class User(BaseModel):
    id : str
    username : str

def create_token(user_id: str, username: str) -> str:
    payload = {
        "sub": user_id,
        "username": username,
        "exp": datetime.utcnow() + timedelta(hours=TOKEN_EXPIRE_HOURS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(credentials : HTTPAuthorizationCredentials = Depends(security)) -> User :
    token = credentials.credentials

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        username = payload.get("username")

        if username is None or user_id is None:
            raise HTTPException(
                status_code=401,
                details="Invalid authentication token",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        #For faster processing, we can use cache to store user lookup so subsequent authorization requests don't require db lookup
        #or get rid of this additional check 
        response = database.table("users").select("*").eq("id", user_id).execute()
        if not response.data:
            raise HTTPException(
                status_code=401,
                details="User no longer exists",
                headers={"WWW-Authenticate": "Bearer"}
            )
        user_data = response.data[0]
        return User(id=user_data["id"], username=user_data["username"])
    except JWTError:
        raise HTTPException(
            status_code=401,
            details="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"}
        )
    except Exception:
        raise HTTPException(
            status_code=401,
            details="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"}
        )

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
        "hashed_password": password_hash,
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
        raise HTTPException(
            status_code=401, 
            detail="Invalid username or password.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    user = response.data[0]

    # Check submitted password against stored hash
    password_matches = bcrypt.checkpw(
        request.password.encode("utf-8"),
        user["hashed_password"].encode("utf-8")
    )
    if not password_matches:
        raise HTTPException(
            status_code=401, 
            detail="Invalid username or password.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    token = create_token(user["id"], user["username"])

    return {"token": token, "username": user["username"]}


@router.post("/auth/logout")
async def logout():
    # JWT tokens are stateless — logout is handled by the frontend deleting the token
    return {"message": "Logged out successfully."}
