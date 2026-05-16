# pyright: reportMissingImports=false
"""
Job Runner — Video Pipeline Entry Point
========================================
Video input is JUST a different input method.
The simulation pipeline is IDENTICAL to manual simulation:
  1. run_pipeline() generates vehicle_added, vehicle_crossed, rl_decision events
  2. Events are POSTed to /simulation/submit-log (same as frontend simulation)
  3. compute_dynamic_metrics() and compute_static_metrics() produce final results
  4. Results stored in DB and served via /simulation/results/{session_id}
"""

import json
import threading
import tempfile
from pathlib import Path

# pyrefly: ignore [missing-import]
import cv2

from backend.ai.perception.video_pipeline import run_pipeline
from backend.core.services.simulation_service import create_session, ensure_session_exists

job_store = {}

BASE_URL = "http://localhost:8000"

# Default config path — created from calibration tool
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "ai" / "perception" / "config" / "junction_demo.json"


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
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 1280)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 720)
    cap.release()
    return total_frames, fps, width, height


def _make_default_config(width: int, height: int) -> dict:
    """
    Generate a sensible default lane config from video dimensions.
    Creates 4 quadrant-based lane regions covering the full frame.
    This works reasonably for any intersection video without calibration.
    """
    cx = width / 2
    cy = height / 2

    # Each lane covers a quadrant + center strip, extending to the edge
    return {
        "lane_regions": {
            "north": {
                "label": "north",
                "direction": "incoming",
                "points": [
                    [cx * 0.2, 0],
                    [cx * 0.8, 0],
                    [cx * 0.8, cy * 0.8],
                    [cx * 0.2, cy * 0.8],
                ]
            },
            "south": {
                "label": "south",
                "direction": "incoming",
                "points": [
                    [cx * 0.2, cy * 1.2],
                    [cx * 0.8, cy * 1.2],
                    [cx * 0.8, height],
                    [cx * 0.2, height],
                ]
            },
            "east": {
                "label": "east",
                "direction": "incoming",
                "points": [
                    [cx * 1.2, cy * 0.2],
                    [width, cy * 0.2],
                    [width, cy * 0.8],
                    [cx * 1.2, cy * 0.8],
                ]
            },
            "west": {
                "label": "west",
                "direction": "incoming",
                "points": [
                    [0, cy * 0.2],
                    [cx * 0.8, cy * 0.2],
                    [cx * 0.8, cy * 0.8],
                    [0, cy * 0.8],
                ]
            }
        },
        "settings": {
            "min_avg_confidence": 0.1,
            "max_count_jump": 5,
            "confidence_hold_ticks": 1,
            "smooth_alpha": 0.2,
            "tracker_min_seen_frames": 2,
            "tracker_max_missed_frames": 10,
        },
        "homography": {
            "enabled": False
        }
    }


def _get_config_path(width: int, height: int) -> Path:
    """
    Returns path to an existing config file, or creates a default one.
    Priority: user-calibrated config > auto-generated default
    """
    # Check for user-calibrated config
    if DEFAULT_CONFIG_PATH.exists():
        print(f"[JOB RUNNER] Using calibrated config: {DEFAULT_CONFIG_PATH}")
        return DEFAULT_CONFIG_PATH

    # Generate a default config and save it for reuse
    config_dir = DEFAULT_CONFIG_PATH.parent
    config_dir.mkdir(parents=True, exist_ok=True)

    default_config = _make_default_config(width, height)
    with open(DEFAULT_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(default_config, f, indent=2)

    print(f"[JOB RUNNER] ⚠️  No calibrated config found. Generated default config at: {DEFAULT_CONFIG_PATH}")
    print(f"[JOB RUNNER] For better results, run: python -m backend.ai.perception.calibrate_lanes_polygon --video <your_video>")
    return DEFAULT_CONFIG_PATH


def _run_pipeline_in_thread(job_id: str, video_path: str, session_id: str, width: int, height: int):
    """
    Run the full video pipeline — identical to simulation.
    Generates vehicle_added, vehicle_crossed, rl_decision events and
    POSTs them to /simulation/submit-log exactly like the frontend does.
    After completion, recomputes and saves final metrics.
    """
    from backend.core.services.simulation_service import save_simulation_results
    from backend.core.services.static_replay_service import compute_dynamic_metrics, compute_static_metrics
    from backend.core.services.results_service import get_events_for_session

    try:
        job_store[job_id]["status"] = "running"

        config_path = _get_config_path(width, height)

        print(f"🚀 [JOB] Starting video pipeline for session={session_id}")
        print(f"[JOB] Video: {video_path}")
        print(f"[JOB] Config: {config_path}")
        print(f"[JOB] Dimensions: {width}x{height}")

        # ── CORE PIPELINE ──────────────────────────────────────────────────────
        # This is identical to what runs during manual simulation.
        # It processes the video frame-by-frame, generates events, and
        # POSTs them to /simulation/submit-log in real-time batches.
        # WebSocket updates fire automatically as events arrive.
        def _update_progress(pct):
            job_store[job_id]["progress"] = pct

        run_pipeline(
            video_path=Path(video_path),
            config_path=config_path,
            base_url=BASE_URL,
            sample_fps=5.0,        # 5 ticks/sec — matches simulation decision rate
            preview=False,
            session_id=session_id,
            realtime=False,        # Batch mode: skip sleep, process as fast as possible
            on_progress=_update_progress,
        )
        # ───────────────────────────────────────────────────────────────────────

        print(f"✅ [JOB] Pipeline complete for session={session_id}. Computing final metrics...")

        # Re-compute final metrics from ALL events in DB
        # (same function used by simulation results endpoint)
        events = get_events_for_session(session_id)
        timer_duration = job_store[job_id].get("timer_duration", 60)

        print(f"📊 [JOB] {len(events)} events found, timer={timer_duration}s")
        dynamic_metrics = compute_dynamic_metrics(events, timer_duration)
        static_metrics = compute_static_metrics(events, timer_duration)

        d_crossed = dynamic_metrics.get('total_vehicles_crossed', 0)
        s_crossed = static_metrics.get('total_vehicles_crossed', 0)
        d_wait = dynamic_metrics.get('avg_wait_time', 0.0)
        s_wait = static_metrics.get('avg_wait_time', 0.0)
        print(f"[JOB] dynamic: crossed={d_crossed}, avg_wait={d_wait:.1f}s")
        print(f"[JOB] static:  crossed={s_crossed}, avg_wait={s_wait:.1f}s")

        # Save final results to DB (overwrites intermediate results)
        save_simulation_results(session_id, dynamic_metrics, static_metrics)

        # Store in job_store for frontend polling (VideoUploadPage reads this)
        job_store[job_id]["video_duration"] = job_store[job_id].get("timer_duration", 0)
        job_store[job_id]["video_events"] = []  # events are in DB; don't bloat memory
        job_store[job_id]["status"] = "completed"
        job_store[job_id]["progress"] = 100

        print(f"🎉 [JOB] Done! Dashboard: /dashboard/{session_id}")

    except Exception as exc:
        import traceback
        traceback.print_exc()
        job_store[job_id]["status"] = "failed"
        job_store[job_id]["error_message"] = str(exc)
        print(f"❌ [JOB] Failed for session={session_id}: {exc}")


async def run_video_pipeline_job(job_id: str, video_path: str):
    """
    Entry point called by POST /jobs/start.
    Sets up the session, reads video stats, then launches pipeline in background.
    """
    if job_id not in job_store:
        job_store[job_id] = _pending_job_state()

    job_store[job_id]["job_id"] = job_id
    job_store[job_id]["status"] = "pending"
    job_store[job_id]["error_message"] = None

    try:
        total_frames, fps, width, height = _safe_video_stats(video_path)
        job_store[job_id]["total_frames"] = max(0, total_frames)
        job_store[job_id]["fps"] = fps

        duration_seconds = int(round(float(total_frames) / max(float(fps), 1.0))) if total_frames > 0 else 120
        timer_duration = max(30, duration_seconds)
        job_store[job_id]["timer_duration"] = timer_duration

        # Reuse the upload session_id as simulation session
        # (same pattern: upload → session → events → results)
        session_id = ensure_session_exists(job_id)
        job_store[job_id]["session_id"] = session_id

        print(f"[JOB RUNNER] job_id={job_id} session_id={session_id} "
              f"frames={total_frames} fps={fps:.1f} duration={timer_duration}s "
              f"dims={width}x{height}")

    except Exception as exc:
        job_store[job_id]["status"] = "failed"
        job_store[job_id]["error_message"] = str(exc)
        print(f"❌ [JOB RUNNER] Setup failed: {exc}")
        return

    thread = threading.Thread(
        target=_run_pipeline_in_thread,
        args=(job_id, video_path, session_id, width, height),
        daemon=True,
    )
    thread.start()
