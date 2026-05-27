import hashlib
import json
from backend.infra.database.db import get_connection

def get_video_hash(video_path):
    """Generate a unique MD5 hash for the video file based on its name and size."""
    import os
    file_info = f"{os.path.basename(video_path)}_{os.path.getsize(video_path)}"
    return hashlib.md5(file_info.encode()).hexdigest()

def save_frame_to_cache(video_hash, frame_idx, lane_counts, ambulances, wait_times):
    """Saves detection results for a specific frame to the database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO video_detections_cache (video_hash, frame_idx, lane_counts, ambulances, wait_times)
        VALUES (?, ?, ?, ?, ?)
    """, (video_hash, frame_idx, json.dumps(lane_counts), json.dumps(ambulances), json.dumps(wait_times)))
    conn.commit()
    conn.close()

def get_cached_video_data(video_hash):
    """Fetches all cached frames for a given video hash."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT frame_idx, lane_counts, ambulances, wait_times 
        FROM video_detections_cache 
        WHERE video_hash = ? 
        ORDER BY frame_idx ASC
    """, (video_hash,))
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        return None
        
    return [
        {
            "frame_idx": r[0],
            "lane_counts": json.loads(r[1]),
            "ambulances": json.loads(r[2]),
            "wait_times": json.loads(r[3])
        }
        for r in rows
    ]

def save_video_events(video_hash, events, duration):
    """Saves the entire event list for a video to the cache."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO video_events_cache (video_hash, events_json, video_duration)
        VALUES (?, ?, ?)
    """, (video_hash, json.dumps(events), float(duration)))
    conn.commit()
    conn.close()

def get_video_events(video_hash):
    """Fetches cached event list for a video."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT events_json, video_duration FROM video_events_cache WHERE video_hash = ?", (video_hash,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            "events": json.loads(row[0]),
            "video_duration": row[1]
        }
    return None

def is_video_cached(video_hash):
    """Checks if any data exists for this video hash."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM video_detections_cache WHERE video_hash = ?", (video_hash,))
    count = cursor.fetchone()[0]
    conn.close()
    return count > 0
