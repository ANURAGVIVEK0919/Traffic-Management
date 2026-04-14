from backend.database.db import get_connection  # Import connection function
import uuid  # For unique session id
from datetime import datetime  # For UTC timestamp
import time
import json
from backend.services.results_service import cache_simulation_results


def ensure_session_exists(session_id):
    """Ensure the parent simulation_session row exists before child inserts."""
    session_id = str(session_id).strip() if session_id is not None else None
    if not session_id:
        return None

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM simulation_session WHERE id = ?", (session_id,))
    row = cursor.fetchone()
    if not row:
        created_at = datetime.utcnow().isoformat()
        cursor.execute(
            """
            INSERT INTO simulation_session (id, timer_duration, created_at, status)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, 0, created_at, "running")
        )
        conn.commit()
    conn.close()
    print("Ensured session exists:", session_id)
    return session_id

def create_session(timer_duration):
	"""Create a new simulation session and return its id."""
	session_id = str(uuid.uuid4())  # Generate unique id
	created_at = datetime.utcnow().isoformat()  # Current UTC time as string
	conn = get_connection()
	cursor = conn.cursor()
	# Insert new session row
	cursor.execute(
		"""
		INSERT INTO simulation_session (id, timer_duration, created_at, status)
		VALUES (?, ?, ?, ?)
		""",
		(session_id, timer_duration, created_at, "running")
	)
	conn.commit()
	conn.close()
	return session_id

def save_event_log(session_id, events):
    import json  # For payload serialization

    conn = get_connection()
    cursor = conn.cursor()
    for event in events or []:
        if not isinstance(event, dict):
            continue
        payload = event.get('payload') or {}
        event_type = event.get('eventType', 'unknown')
        timestamp = event.get('timestamp', 0)
        cursor.execute(
            """
            INSERT INTO simulation_event (session_id, timestamp, event_type, lane_id, vehicle_type, vehicle_id, payload)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                timestamp,
                event_type,
                event.get('laneId', None),
                event.get('vehicleType', None),
                event.get('vehicleId', None),
                json.dumps(payload)
            )
        )
        if event_type in ('rl_decision', 'signal_phase'):
            selected_lane = payload.get('lane') if isinstance(payload, dict) else None
            if selected_lane is None:
                selected_lane = event.get('laneId')
            duration = payload.get('duration') if isinstance(payload, dict) else None
            debug = payload.get('debug', {}) if isinstance(payload, dict) else {}

            print("FINAL LOG:", selected_lane, duration)

            if selected_lane is None or duration is None:
                continue

            cursor.execute(
                """
                INSERT INTO simulation_decision_log (
                    session_id, tick_number, timestamp, selected_lane, duration, strategy, snapshot, decision_debug
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    payload.get('tick', None),
                    timestamp,
                    selected_lane or event.get('laneId') or 'unknown',
                    duration,
                    (debug.get('strategy', None) if isinstance(debug, dict) else None),
                    json.dumps(payload.get('snapshot', {})),
                    json.dumps(debug)
                )
            )
    conn.commit()
    conn.close()
    return { "success": True }


def save_signal_log(session_id, lane, duration):
    session_id = str(session_id).strip() if session_id is not None else None
    if not session_id:
        return {"error": "Missing session_id"}

    selected_lane = str(lane or '').strip().lower()
    if not selected_lane:
        return {"error": "Missing lane"}

    try:
        duration_value = float(duration)
    except (TypeError, ValueError):
        return {"error": "Invalid duration"}

    ensure_session_exists(session_id)

    conn = get_connection()
    cursor = conn.cursor()
    timestamp = float(time.time() * 1000.0)
    payload = {
        "lane": selected_lane,
        "duration": duration_value,
    }

    print("FINAL LOG:", selected_lane, duration_value)

    cursor.execute(
        """
        INSERT INTO simulation_decision_log (
            session_id, tick_number, timestamp, selected_lane, duration, strategy, snapshot, decision_debug
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            None,
            timestamp,
            selected_lane,
            duration_value,
            "simulation_phase",
            json.dumps({}),
            json.dumps(payload),
        )
    )
    conn.commit()
    conn.close()
    return {"success": True}

def save_simulation_results(session_id, dynamic_metrics, static_metrics):
    from datetime import datetime  # For timestamp
    session_id = str(session_id).strip() if session_id is not None else None
    if not session_id:
        return {"error": "Missing session_id"}

    try:
        ensure_session_exists(session_id)
        conn = get_connection()
        cursor = conn.cursor()
        created_at = datetime.utcnow().isoformat()
        # Insert dynamic metrics
        cursor.execute(
            """
            INSERT INTO simulation_result (
                session_id, system_type, avg_wait_time, total_vehicles_crossed, co2_estimate,
                avg_green_utilization, ambulance_avg_wait_time, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                "dynamic",
                dynamic_metrics.get('avg_wait_time'),
                dynamic_metrics.get('total_vehicles_crossed'),
                dynamic_metrics.get('co2_estimate'),
                dynamic_metrics.get('avg_green_utilization'),
                dynamic_metrics.get('ambulance_avg_wait_time'),
                created_at
            )
        )
        # Insert static metrics
        cursor.execute(
            """
            INSERT INTO simulation_result (
                session_id, system_type, avg_wait_time, total_vehicles_crossed, co2_estimate,
                avg_green_utilization, ambulance_avg_wait_time, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                "static",
                static_metrics.get('avg_wait_time'),
                static_metrics.get('total_vehicles_crossed'),
                static_metrics.get('co2_estimate'),
                static_metrics.get('avg_green_utilization'),
                static_metrics.get('ambulance_avg_wait_time'),
                created_at
            )
        )
        conn.commit()
        conn.close()
        cache_simulation_results(session_id, dynamic_metrics, static_metrics)
        return {"success": True}
    except Exception as e:
        print("❌ DB SAVE ERROR:", e)
        raise
