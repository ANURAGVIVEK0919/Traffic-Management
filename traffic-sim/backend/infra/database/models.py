

import json
from .db import get_connection  # Import connection function

def create_tables():
	"""Create required tables if they do not exist."""
	conn = get_connection()
	cursor = conn.cursor()
	# Table 1: simulation_session
	cursor.execute("""
		CREATE TABLE IF NOT EXISTS simulation_session (
			id TEXT PRIMARY KEY,
			timer_duration INTEGER NOT NULL,
			created_at TEXT NOT NULL,
			status TEXT NOT NULL
		)
	""")
	# Table 2: simulation_event
	cursor.execute("""
		CREATE TABLE IF NOT EXISTS simulation_event (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			session_id TEXT NOT NULL,
			timestamp REAL NOT NULL,
			event_type TEXT NOT NULL,
			lane_id TEXT,
			vehicle_type TEXT,
			vehicle_id TEXT,
			payload TEXT,
			FOREIGN KEY (session_id) REFERENCES simulation_session(id)
		)
	""")
	# Table 3: simulation_result
	cursor.execute("""
		CREATE TABLE IF NOT EXISTS simulation_result (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			session_id TEXT NOT NULL,
			system_type TEXT NOT NULL,
			avg_wait_time REAL,
			total_vehicles_crossed INTEGER,
			co2_estimate REAL,
			avg_green_utilization REAL,
			ambulance_avg_wait_time REAL,
			created_at TEXT NOT NULL,
			FOREIGN KEY (session_id) REFERENCES simulation_session(id)
		)
	""")
	# Table 4: simulation_decision_log
	cursor.execute("""
		CREATE TABLE IF NOT EXISTS simulation_decision_log (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			session_id TEXT NOT NULL,
			tick_number INTEGER,
			timestamp REAL NOT NULL,
			selected_lane TEXT NOT NULL,
			duration INTEGER,
			strategy TEXT,
			snapshot TEXT,
			decision_debug TEXT,
			FOREIGN KEY (session_id) REFERENCES simulation_session(id)
		)
	""")

	# Table 5: shared_state (for lane counts, timer, etc.)
	cursor.execute("""
		CREATE TABLE IF NOT EXISTS shared_state (
			key TEXT PRIMARY KEY,
			value TEXT NOT NULL
		)
	""")
	# Table 6: video_detections_cache (for reusable video data)
	cursor.execute("""
		CREATE TABLE IF NOT EXISTS video_detections_cache (
			video_hash TEXT,
			frame_idx INTEGER,
			lane_counts TEXT, -- JSON string
			ambulances TEXT,  -- JSON string
			wait_times TEXT,   -- JSON string
			PRIMARY KEY (video_hash, frame_idx)
		)
	""")

	cursor.execute("""
		CREATE INDEX IF NOT EXISTS idx_simulation_decision_log_session
		ON simulation_decision_log (session_id)
	""")

	cursor.execute("""
		CREATE INDEX IF NOT EXISTS idx_simulation_event_session
		ON simulation_event (session_id)
	""")

	# Table 7: video_events_cache (for UI fast-start)
	cursor.execute("""
		CREATE TABLE IF NOT EXISTS video_events_cache (
			video_hash TEXT PRIMARY KEY,
			events_json TEXT,
			video_duration REAL
		)
	""")

	conn.commit()
	conn.commit()

	# Initialize default shared state if not present
	cursor.execute("SELECT COUNT(*) FROM shared_state")
	if cursor.fetchone()[0] == 0:
		cursor.execute("INSERT INTO shared_state (key, value) VALUES (?, ?)", ("lane_counts", json.dumps([0,0,0,0])))
		cursor.execute("INSERT INTO shared_state (key, value) VALUES (?, ?)", ("timer", json.dumps(0)))
		conn.commit()

	conn.close()
