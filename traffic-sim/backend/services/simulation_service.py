from backend.database.db import get_connection  # Import connection function
import uuid  # For unique session id
from datetime import datetime  # For UTC timestamp

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
    for event in events:
        cursor.execute(
            """
            INSERT INTO simulation_event (session_id, timestamp, event_type, lane_id, vehicle_type, vehicle_id, payload)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                event['timestamp'],
                event['eventType'],
                event.get('laneId', None),
                event.get('vehicleType', None),
                event.get('vehicleId', None),
                json.dumps(event.get('payload', {}))
            )
        )
    conn.commit()
    conn.close()
    return { "success": True }

def save_simulation_results(session_id, dynamic_metrics, static_metrics):
    from datetime import datetime  # For timestamp
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
    return { "success": True }
