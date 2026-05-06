import json
from .db import get_connection

def set_shared_state(key, value):
    """Set a value in the shared_state table (value is JSON-serialized)."""
    conn = get_connection()
    cursor = conn.cursor()
    value_json = json.dumps(value)
    cursor.execute("""
        INSERT INTO shared_state (key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
    """, (key, value_json))
    conn.commit()
    conn.close()


def get_shared_state(key, default=None):
    """Get a value from the shared_state table (returns deserialized JSON, or default)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM shared_state WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    if row:
        try:
            return json.loads(row[0])
        except Exception:
            return default
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
    


