from backend.services.simulation_service import create_session  # Import service function
from backend.services.simulation_service import save_event_log, save_simulation_results
from backend.services.static_replay_service import compute_dynamic_metrics, compute_static_metrics
from backend.services.results_service import get_simulation_results, format_comparison
from backend.database.db import get_connection


def handle_create_session(timer_duration):
	"""Controller: create session and return its id."""
	session_id = create_session(timer_duration)  # Call service
	return {"session_id": session_id}  # Return response

# Handle event log submission and metrics computation
def handle_submit_log(session_id, events):
	save_event_log(session_id, events)
	# Fetch timer_duration from DB
	conn = get_connection()
	cursor = conn.cursor()
	cursor.execute("SELECT timer_duration FROM simulation_session WHERE id = ?", (session_id,))
	row = cursor.fetchone()
	conn.close()
	timer_duration = row[0] if row else 0
	# Compute metrics
	dynamic_metrics = compute_dynamic_metrics(events, timer_duration)
	static_metrics = compute_static_metrics(events, timer_duration)
	save_simulation_results(session_id, dynamic_metrics, static_metrics)
	return {"success": True}

# Handle result retrieval
def handle_get_results(session_id):
	# Fetch results from service
	results = get_simulation_results(session_id)
	if "error" in results:
		return results
	# Format and return comparison
	return format_comparison(session_id, results["dynamic"], results["static"])
