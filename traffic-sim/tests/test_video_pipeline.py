"""
Test Suite 3: Video Pipeline & YOLO Inference
Tests video upload, background job processing, and detection logging.
"""

import requests
import time
import unittest
import os
from pathlib import Path

BASE_URL = "http://localhost:8000"
# Using the video file provided by the user
VIDEO_FILENAME = "6a4ac5b4-9210-4e9b-b272-086eb6f81696_WhatsApp Video 2026-04-15 at 5.07.17 PM.mp4"
VIDEO_PATH = Path(r"e:\Traffic Managment\Traffic-Management\traffic-sim\uploads") / VIDEO_FILENAME

class TestVideoPipeline(unittest.TestCase):
    def setUp(self):
        if not VIDEO_PATH.exists():
            self.skipTest(f"Video file not found at {VIDEO_PATH}. Ensure the file exists.")

    def test_video_processing_flow(self):
        print(f"Starting Video Processing Test for: {VIDEO_FILENAME}")
        
        # 1. Start processing job
        # Note: We use the existing file in the uploads folder
        session_id = "test-session-" + str(int(time.time()))
        resp = requests.post(f"{BASE_URL}/jobs/start", json={
            "session_id": session_id,
            "video_path": str(VIDEO_PATH)
        })
        self.assertEqual(resp.status_code, 200, "Should start processing job successfully.")
        job_data = resp.json()
        job_id = job_data.get("job_id")
        self.assertTrue(job_id, "Job ID must be returned.")
        
        print(f"Job ID (Session ID): {job_id}")

        # 2. Poll Status (Wait for some progress)
        max_retries = 15
        started = False
        for i in range(max_retries):
            status_resp = requests.get(f"{BASE_URL}/jobs/{job_id}/status").json()
            progress = status_resp.get("progress", 0)
            state = status_resp.get("status", "unknown")
            print(f"Polling Status: {state} | Progress: {progress}%")
            
            if progress > 0 or state == "completed":
                started = True
                break
            if state == "error":
                self.fail(f"Job failed with error: {status_resp.get('error_message')}")
            time.sleep(3)
        
        self.assertTrue(started, "Video processing should show progress within 45 seconds.")

        # 3. Verify Database Entries
        # Check if any events were logged
        events = requests.get(f"{BASE_URL}/simulation/results/{session_id}").json()
        self.assertIn("actual_signal_log", events)
        print("Database connectivity for video results verified.")

if __name__ == "__main__":
    unittest.main()
