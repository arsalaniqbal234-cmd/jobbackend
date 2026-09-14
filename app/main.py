import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import origins
from app.observability import report_failure, setup_monitoring
from app.routers import health, jobs, saved_searches

setup_monitoring()
app = FastAPI(title="Rozgar API", version="0.8.0")
app.add_middleware(
    CORSMiddleware, allow_origins=origins(), allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"], allow_headers=["Authorization", "Content-Type", "X-API-Key"],
    expose_headers=["X-Cache", "Server-Timing", "X-Request-ID"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = uuid.uuid4().hex
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as error:
        report_failure("api", error)
        response = JSONResponse(status_code=500, content={
            "detail": "Something went wrong. Please try again.", "request_id": request_id,
        })
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Response-Time-Ms"] = f"{(time.perf_counter()-start)*1000:.2f}"
    if request.url.path.startswith(("/saved-searches", "/health")):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/")
def home():
    return {"message": "Rozgar API running"}


app.include_router(jobs.router)
app.include_router(saved_searches.router)
app.include_router(health.router)
