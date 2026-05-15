from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from backend.job_runner import job_store, run_video_pipeline_job

router = APIRouter()


class StartJobRequest(BaseModel):
    session_id: str
    video_path: str


@router.post("/jobs/start")
async def start_job(request: StartJobRequest, background_tasks: BackgroundTasks):
    # Validate session_id used as job id
    if not request.session_id:
        raise HTTPException(status_code=400, detail="Invalid session_id")

    job_id = request.session_id
    job_store[job_id] = {
        "job_id": job_id,
        "status": "pending",
        "progress": 0,
        "total_frames": 0,
        "processed_frames": 0,
        "error_message": None,
    }
    background_tasks.add_task(run_video_pipeline_job, job_id, request.video_path)
    job_response = job_store[job_id]
    job_response["session_id"] = job_id
    print(f"🚀 /jobs/start RESPONSE: {job_response}")
    return job_response


@router.get("/jobs/{session_id}/status")
def get_job_status(session_id: str):
    if session_id not in job_store:
        raise HTTPException(status_code=404, detail="Job not found")
    return job_store[session_id]
