"""
Explainer Validation Script (Dual Mode)
Verifies that the AI Explainer works for both Live Simulation and Video Playback states.
"""
import requests
import sqlite3
import unittest
import os

BASE_URL = "http://localhost:8000"
DB_PATH = r"e:\Traffic Managment\Traffic-Management\traffic-sim\traffic_sim.db"

class TestExplainerDualMode(unittest.TestCase):
    def test_simulation_mode_explanation(self):
        print("\n--- Testing Explainer: Simulation Mode (Live) ---")
        live_state = {
            "lane_counts": {"north": 15, "south": 2, "east": 1, "west": 1},
            "wait_times": {"north": 45, "south": 5, "east": 5, "west": 5},
            "ambulance": {"north": False, "south": False, "east": False, "west": False},
            "current_lane": "north",
            "decision_made": 25.0
        }
        resp = requests.post(f"{BASE_URL}/signal/explain", json=live_state)
        self.assertEqual(resp.status_code, 200)
        print("PASS: AI successfully explained the live simulation state.")
        print(f"AI Said: {resp.json()['explanation'][:100]}...")

    def test_video_mode_explanation(self):
        print("\n--- Testing Explainer: Video Mode (Historical) ---")
        # Fetch a state from the database (from a processed video session)
        if not os.path.exists(DB_PATH):
            self.skipTest("Database not found for historical check.")
            
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT selected_lane, duration, snapshot FROM simulation_decision_log LIMIT 1")
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            self.skipTest("No video decision logs found in DB yet.")
            
        lane, duration, snapshot_json = row
        import json
        snapshot = json.loads(snapshot_json) if snapshot_json else {}
        
        # Prepare historical request
        hist_state = {
            "lane_counts": snapshot.get("lane_counts", {"north": 5, "south": 5, "east": 5, "west": 5}),
            "wait_times": snapshot.get("wait_times", {"north": 10, "south": 10, "east": 10, "west": 10}),
            "ambulance": {"north": False, "south": False, "east": False, "west": False},
            "current_lane": lane,
            "decision_made": duration
        }
        
        resp = requests.post(f"{BASE_URL}/signal/explain", json=hist_state)
        self.assertEqual(resp.status_code, 200)
        print(f"PASS: AI successfully explained the historical video state (Lane: {lane}).")
        print(f"AI Said: {resp.json()['explanation'][:100]}...")

if __name__ == "__main__":
    unittest.main()
