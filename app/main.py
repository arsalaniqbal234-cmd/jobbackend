from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import jobs

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://jobsi-ten.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def home():
    return {"message": "job platform running api"}

app.include_router(jobs.router)