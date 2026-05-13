# pyright: reportMissingImports=false

import threading
from pathlib import Path

# pyrefly: ignore [missing-import]
import cv2

from backend.perception.state_extractor import extract_initial_state, extract_full_pipeline_data
from backend.perception.video_pipeline import run_pipeline
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
    from backend.services.simulation_service import save_event_log, save_simulation_results
    from backend.services.static_replay_service import compute_dynamic_metrics, compute_static_metrics
    try:
        job_store[job_id]["status"] = "running"

        # Step 1: Full Video Scan (Pre-processing)
        job_store[job_id]["status"] = "processing"
        print(f"🚀 [JOB] Starting full video scan for {session_id}")
        
        scan_results = extract_full_pipeline_data(
            video_path=video_path,
            config_path=config_path,
            progress_callback=lambda p: job_store[job_id].update({"progress": p})
        )
        
        events = scan_results.get("events", [])
        
        # Step 2: Persist results to Database
        print(f"💾 [JOB] Saving {len(events)} events to database for {session_id}")
        save_event_log(session_id, events)
        
        # Step 3: Compute and Save Metrics for Dashboard
        print(f"📊 [JOB] Computing metrics for {session_id}")
        timer_duration = job_store[job_id].get("timer_duration", 60)
        dynamic_metrics = compute_dynamic_metrics(events, timer_duration)
        static_metrics = compute_static_metrics(events, timer_duration)
        
        save_simulation_results(session_id, dynamic_metrics, static_metrics)
        
        # Store for frontend playback
        job_store[job_id]["video_events"] = events
        job_store[job_id]["video_duration"] = scan_results.get("video_duration", 0.0)
        job_store[job_id]["status"] = "completed"
        
        print(f"✅ [JOB] Processing complete for {session_id}. Dashboard data ready.")
    except Exception as exc:
        import traceback
        traceback.print_exc()
        job_store[job_id]["status"] = "failed"
        job_store[job_id]["error_message"] = str(exc)

async def run_video_pipeline_job(job_id, video_path):
    from backend.services.simulation_service import ensure_session_exists
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
        
        # Use the job_id (upload session_id) instead of creating a new one
        session_id = ensure_session_exists(job_id)
        job_store[job_id]["session_id"] = session_id
        job_store[job_id]["timer_duration"] = timer_duration
    except Exception as exc:
        job_store[job_id]["status"] = "failed"
        job_store[job_id]["error_message"] = str(exc)
        return
    
    project_root = Path(__file__).resolve().parents[1]
    config_path = None # Standard config used by default
    
    thread = threading.Thread(
        target=_run_extractor_in_thread,
        args=(job_id, video_path, config_path, session_id),
        daemon=True
    )
    thread.start()
