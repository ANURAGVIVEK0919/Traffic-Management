DEBUG = False
from backend.core.services.simulation_service import create_session
from backend.core.services.simulation_service import ensure_session_exists, save_event_log, save_simulation_results, save_signal_log
from backend.core.services.static_replay_service import compute_dynamic_metrics, compute_static_metrics
from backend.core.services.results_service import get_simulation_results, format_comparison, get_decision_logs
from backend.infra.database.db import get_connection
from backend.ai.perception.session_report import build_report
from backend.job_runner import job_store
from backend.infra.shared_memory import latest_results, latest_results_lock
from fastapi.responses import JSONResponse


def _safe_metric_value(value):
	return 0 if value is None else value


def _sanitize_metrics(metrics):
	if not isinstance(metrics, dict):
		return {}
	return {key: _safe_metric_value(value) for key, value in metrics.items()}


def handle_create_session(timer_duration):
	"""Controller: create session and return its id."""
	# Block manual session creation if video processing is active
	from backend.infra.database.shared_state import is_video_processing_active
	if is_video_processing_active():
		return {"success": False, "error": "Manual input is disabled while video processing is active."}

	session_id = create_session(timer_duration)  # Call service
	if not session_id:
		print("❌ ERROR: session_id is None or empty!")
		return {"success": False, "error": "Failed to create session"}
	response = {"success": True, "session_id": session_id}
	print(f"🚀 /simulation/start RESPONSE: {response}")
	return response


def resolve_session_id(identifier):
	"""Resolve an incoming endpoint id to a valid session id."""
	if not identifier:
		return identifier

	conn = get_connection()
	cursor = conn.cursor()
	cursor.execute("SELECT id FROM simulation_session WHERE id = ?", (identifier,))
	row = cursor.fetchone()
	conn.close()
	if row:
		return identifier

	job_entry = job_store.get(identifier)
	if isinstance(job_entry, dict):
		mapped = job_entry.get('session_id') or job_entry.get('sessionId')
		if mapped:
			return mapped

	return identifier

# Handle event log submission and metrics computation
def handle_submit_log(session_id, events):
    import os
    from backend.core.services.results_service import get_events_for_session
    try:
        session_id = resolve_session_id(session_id)
        if DEBUG:
            print(f"[CONTROLLER] submit received session={session_id} PID={os.getpid()}")
            print(f"[CONTROLLER] event count={len(events) if events else 0}")
        
        if not session_id:
            return JSONResponse(status_code=400, content={"error": "Invalid session_id"})
        if not isinstance(events, list) or not events:
            return JSONResponse(status_code=400, content={"error": "Invalid events"})
        
        ensure_session_exists(session_id)
        save_event_log(session_id, events)
        
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT timer_duration FROM simulation_session WHERE id = ?", (session_id,))
        row = cursor.fetchone()
        conn.close()
        timer_duration = row[0] if row else 0

        # ✅ FIX: Compute metrics from ALL session events (not just current batch)
        # This ensures correct incremental results throughout the video pipeline
        all_session_events = get_events_for_session(session_id)
        dynamic_results = compute_dynamic_metrics(all_session_events, timer_duration)
        static_results = compute_static_metrics(all_session_events, timer_duration)
        
        if DEBUG: print(f"[CONTROLLER] metrics from {len(all_session_events)} total events")

        # Extract latest lane state for WebSocket broadcast
        lane_counts = [0, 0, 0, 0]
        active_lane = "north"
        duration = 5

        for event in reversed(events):
            if isinstance(event, dict) and event.get("eventType") == "rl_decision":
                snapshot = event.get("payload", {}).get("snapshot", {})
                lane_state = snapshot.get("lane_state", {})

                lane_counts = [
                    int(lane_state.get("north", {}).get("count", 0)) if isinstance(lane_state.get("north"), dict) else int(lane_state.get("north", 0)),
                    int(lane_state.get("south", {}).get("count", 0)) if isinstance(lane_state.get("south"), dict) else int(lane_state.get("south", 0)),
                    int(lane_state.get("east", {}).get("count", 0)) if isinstance(lane_state.get("east"), dict) else int(lane_state.get("east", 0)),
                    int(lane_state.get("west", {}).get("count", 0)) if isinstance(lane_state.get("west"), dict) else int(lane_state.get("west", 0)),
                ]
                active_lane = event.get("laneId") or snapshot.get("active_lane")
                duration = snapshot.get("duration", 5)

                if DEBUG: print(f"[CONTROLLER] counts extracted={lane_counts} active={active_lane}")
                break
        
        counts = lane_counts

        dynamic_results = _sanitize_metrics(dynamic_results)
        static_results = _sanitize_metrics(static_results)

        try:
            save_simulation_results(session_id, dynamic_results, static_results)
            with latest_results_lock:
                latest_results[session_id] = {
                    "lane_counts": counts,
                    "active_lane": active_lane,
                    "duration": duration
                }
                latest_results['lane_counts'] = counts # legacy fallback
                print(f"[MEMORY] session={session_id} counts={counts}")

        except Exception as e:
            print("❌ DB SAVE ERROR:", e)
            raise
        print(f"[SUBMIT LOG] save_simulation_results done")
        return {"success": True}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})



# Handle result retrieval
def handle_get_results(session_id):
    session_id = resolve_session_id(session_id)
    # Fetch results from service
    results = get_simulation_results(session_id)
    if results is None or not isinstance(results, dict):
        results = {}
    if "error" in results:
        results.setdefault('dynamic', {'lane_state': {'north': 0, 'south': 0, 'east': 0, 'west': 0}})
        results.setdefault('static', {'lane_state': {'north': 0, 'south': 0, 'east': 0, 'west': 0}})
        results.setdefault('actual_signal_log', [])
        return results
    # Format and return comparison
    return format_comparison(
        session_id,
        results["dynamic"],
        results["static"],
        results.get("actual_signal_log", []),
        results.get("signal_phases", []),
    )


def handle_get_results_compare(rl_id, static_id):
    rl_session_id = resolve_session_id(rl_id)
    static_session_id = resolve_session_id(static_id)
    rl_results = get_simulation_results(rl_session_id)
    static_results = get_simulation_results(static_session_id)

    if not isinstance(rl_results, dict) or "error" in rl_results:
        rl_results = {'dynamic': {'lane_state': {'north': 0, 'south': 0, 'east': 0, 'west': 0}}}
    if not isinstance(static_results, dict) or "error" in static_results:
        static_results = {'dynamic': {'lane_state': {'north': 0, 'south': 0, 'east': 0, 'west': 0}}}

    comparison_id = f"{rl_session_id}__vs__{static_session_id}"
    return format_comparison(comparison_id, rl_results.get("dynamic", {}), static_results.get("dynamic", {}))


def handle_get_latest_results(session_id=None):
    import os
    try:
        from backend.infra.database.shared_state import get_lane_counts
        db_counts = get_lane_counts()
        
        state = {"lane_counts": db_counts, "active_lane": "north"}
        
        with latest_results_lock:
            # Also check if there's a more specific session state in memory
            if session_id and session_id in latest_results:
                val = latest_results[session_id]
                if isinstance(val, dict):
                    state = {**val, "lane_counts": db_counts}

        if DEBUG: print(f"[API] Returning latest state: {state}")

        return {
            **state,
            "source": "video"
        }
    except Exception as exc:
        print("❌ LATEST COUNTS FETCH ERROR:", exc)
        return {"lane_counts": [0, 0, 0, 0], "source": "video"}


def handle_get_decision_logs(session_id):
    session_id = resolve_session_id(session_id)
    return {"sessionId": session_id, "decisionLogs": get_decision_logs(session_id)}


def handle_get_session_report(session_id):
    session_id = resolve_session_id(session_id)
    return build_report(session_id)


def handle_log_signal(session_id, lane, duration):
    session_id = resolve_session_id(session_id)
    if not session_id:
        return JSONResponse(status_code=400, content={"error": "Invalid session_id"})

    result = save_signal_log(session_id, lane, duration)
    if isinstance(result, dict) and result.get("error"):
        return JSONResponse(status_code=400, content=result)
    return result
