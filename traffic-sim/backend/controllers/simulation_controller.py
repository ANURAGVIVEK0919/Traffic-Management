from backend.services.simulation_service import create_session  # Import service function
from backend.services.simulation_service import ensure_session_exists, save_event_log, save_simulation_results, save_signal_log
from backend.services.static_replay_service import compute_dynamic_metrics, compute_static_metrics
from backend.services.results_service import get_simulation_results, format_comparison, get_decision_logs
from backend.database.db import get_connection
from backend.perception.session_report import build_report
from backend.job_runner import job_store
from backend.state.simulation_state import latest_results, latest_results_lock
from fastapi.responses import JSONResponse


def _safe_metric_value(value):
	return 0 if value is None else value


def _sanitize_metrics(metrics):
	if not isinstance(metrics, dict):
		return {}
	return {key: _safe_metric_value(value) for key, value in metrics.items()}


def handle_create_session(timer_duration):
	"""Controller: create session and return its id."""
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
	try:
		session_id = resolve_session_id(session_id)
		print(f"SESSION: {session_id}")
		print(f"EVENTS TYPE: {type(events)}")
		print(f"EVENT COUNT: {len(events) if events else 0}")
		print(f"EVENT SAMPLE: {events[:2] if isinstance(events, list) else events}")
		print(f"BACKEND received session_id: {session_id}")
		if not session_id:
			return JSONResponse(status_code=400, content={"error": "Invalid session_id"})
		if not isinstance(events, list) or not events:
			return JSONResponse(status_code=400, content={"error": "Invalid events"})
		ensure_session_exists(session_id)
		print(f"[SUBMIT LOG] session_id={session_id} events={len(events)}")
		save_event_log(session_id, events)
		# Fetch timer_duration from DB
		conn = get_connection()
		cursor = conn.cursor()
		cursor.execute("SELECT timer_duration FROM simulation_session WHERE id = ?", (session_id,))
		row = cursor.fetchone()
		conn.close()
		timer_duration = row[0] if row else 0
		# Compute metrics
		dynamic_results = compute_dynamic_metrics(events, timer_duration)
		static_results = compute_static_metrics(events, timer_duration)

		print(f"[SAVE RESULTS] session_id={session_id}")
		print(f"DYNAMIC: {dynamic_results}")
		print(f"STATIC: {static_results}")
		if not dynamic_results:
			raise RuntimeError(f"Dynamic results missing for session {session_id}")
		if not static_results:
			static_results = dynamic_results.copy()

		dynamic_results = _sanitize_metrics(dynamic_results)
		static_results = _sanitize_metrics(static_results)

		print("[SUBMIT LOG] calling save_simulation_results")
		try:
			save_result = save_simulation_results(session_id, dynamic_results, static_results)
		except Exception as e:
			print("❌ DB SAVE ERROR:", e)
			raise
		print(f"[SUBMIT LOG] save_simulation_results result={save_result}")
		if isinstance(save_result, dict) and save_result.get("error"):
			return JSONResponse(status_code=500, content=save_result)
		return {"success": True}
	except Exception as e:
		import traceback
		print("🔥 BACKEND ERROR:", str(e))
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


def handle_get_latest_results():
	try:
		with latest_results_lock:
			lane_counts = latest_results.get('lane_counts', [0, 0, 0, 0])
			counts = [
				int(lane_counts[0] if len(lane_counts) > 0 else 0),
				int(lane_counts[1] if len(lane_counts) > 1 else 0),
				int(lane_counts[2] if len(lane_counts) > 2 else 0),
				int(lane_counts[3] if len(lane_counts) > 3 else 0),
			]

		print("API RETURN:", counts)

		return {
			"lane_counts": counts,
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
