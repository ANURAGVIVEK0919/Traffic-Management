import json
import sqlite3
import os

DB_PATH = os.path.join(os.getcwd(), "shared_state.db")

def get_shared_conn():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    # WAL mode is critical for concurrent Read/Write on Windows
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE IF NOT EXISTS shared_state (key TEXT PRIMARY KEY, value TEXT)")
    return conn

def set_shared_state(key, value):
    """Set a value in the shared_state table."""
    try:
        conn = get_shared_conn()
        cursor = conn.cursor()
        value_json = json.dumps(value)
        cursor.execute("""
            INSERT INTO shared_state (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
        """, (key, value_json))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"❌ SHARED STATE WRITE ERROR: {e}")

def get_shared_state(key, default=None):
    """Get a value from the shared_state table."""
    try:
        conn = get_shared_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM shared_state WHERE key = ?", (key,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return json.loads(row[0])
        return default
    except Exception as e:
        print(f"❌ SHARED STATE READ ERROR: {e}")
        return default

# Convenience wrappers for lane counts and timer
def set_lane_counts(lane_counts):
    set_shared_state("lane_counts", lane_counts)

def get_lane_counts():
    return get_shared_state("lane_counts", [0, 0, 0, 0])

def set_timer(timer):
    set_shared_state("timer", timer)

def get_timer():
    return get_shared_state("timer", 0)

# Video processing active flag
def set_video_processing_active(active: bool):
    set_shared_state("video_processing_active", bool(active))

def is_video_processing_active():
    return bool(get_shared_state("video_processing_active", False))
    


