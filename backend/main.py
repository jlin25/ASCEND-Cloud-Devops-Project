from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import auth, tasks

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
@app.get("/")
def home():
    return {"status": "backend running"}
    
@app.get("/api/message")
def get_message():
    return {"message": "Hello from FastAPI 🚀"}

app.include_router(auth.router)
app.include_router(tasks.router)