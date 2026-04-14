# pyright: reportMissingImports=false

import threading
from pathlib import Path

import cv2

from backend.perception.state_extractor import extract_initial_state
from backend.services.simulation_service import create_session

job_store = {}


def _pending_job_state():
    return {
        "status": "pending",
        "progress": 0,
        "total_frames": 0,
        "processed_frames": 0,
        "error_message": None,
    }


def _safe_video_stats(video_path: str):
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    cap.release()
    return total_frames, fps


def _run_extractor_in_thread(job_id, video_path, config_path, session_id):
    try:
        job_store[job_id]["status"] = "running"

        extracted = extract_initial_state(
            video_path=Path(video_path),
            config_path=Path(config_path),
            seconds_to_process=3.0,
            min_confidence=0.4,
            min_track_frames=5,
        )

        job_store[job_id]["session_id"] = session_id
        job_store[job_id]["lane_vehicles"] = extracted.get("lane_vehicles", {})
        job_store[job_id]["lane_counts"] = extracted.get("lane_counts", {})
        job_store[job_id]["simulation_state"] = extracted.get("simulation_state", {"lanes": {}})
        job_store[job_id]["processed_frames"] = extracted.get("processed_frames", 0)
        job_store[job_id]["max_frames"] = extracted.get("max_frames", 0)
        job_store[job_id]["seconds_processed"] = extracted.get("seconds_processed", 0.0)
        job_store[job_id]["progress"] = 100
        job_store[job_id]["status"] = "completed"
    except Exception as exc:
        job_store[job_id]["status"] = "failed"
        job_store[job_id]["error_message"] = str(exc)

async def run_video_pipeline_job(job_id, video_path):
    if job_id not in job_store:
        job_store[job_id] = _pending_job_state()
    job_store[job_id]["job_id"] = job_id
    job_store[job_id]["status"] = "pending"
    job_store[job_id]["error_message"] = None
    try:
        total_frames, fps = _safe_video_stats(video_path)
        job_store[job_id]["total_frames"] = max(0, total_frames)
        duration_seconds = int(round(float(total_frames) / max(float(fps), 1.0))) if total_frames > 0 else 120
        timer_duration = max(30, duration_seconds)
        session_id = create_session(timer_duration)
        job_store[job_id]["session_id"] = session_id
        job_store[job_id]["timer_duration"] = timer_duration
    except Exception as exc:
        job_store[job_id]["status"] = "failed"
        job_store[job_id]["error_message"] = str(exc)
        return
    project_root = Path(__file__).resolve().parents[1]
    config_path = project_root / "backend" / "perception" / "config" / "junction_demo.json"
    print(f"Config path: {config_path}")
    if not config_path.exists():
        job_store[job_id]["status"] = "failed"
        job_store[job_id]["error_message"] = f"Config file not found: {config_path}"
        return
    thread = threading.Thread(
        target=_run_extractor_in_thread,
        args=(job_id, video_path, config_path, session_id),
        daemon=True
    )
    thread.start()
