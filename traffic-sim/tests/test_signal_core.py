"""
Test Suite 1: Signal Core Logic & AI Optimization
Tests adaptive durations, constraints, and standard transitions.
"""

import requests
import time
import unittest

BASE_URL = "http://localhost:8000"

class TestSignalCore(unittest.TestCase):
    def setUp(self):
        # Start a fresh session for each test
        resp = requests.post(f"{BASE_URL}/simulation/start", json={"timer_duration": 120}).json()
        self.session_id = resp["session_id"]
        print(f"\n[Setup] Started Session: {self.session_id}")

    def test_adaptive_duration_increase(self):
        """Test if AI increases duration for high traffic lanes."""
        print("Testing AI duration adaptation...")
        
        # Scenario 1: Low Traffic
        low_state = {
            "lane_counts": {"north": 2, "south": 1, "east": 1, "west": 1},
            "wait_times": {"north": 5, "south": 5, "east": 5, "west": 5},
            "ambulance": {"north": False, "south": False, "east": False, "west": False},
            "current_lane": "north"
        }
        resp_low = requests.post(f"{BASE_URL}/signal/decision", json=low_state).json()
        duration_low = resp_low["recommended_duration"]
        
        # Scenario 2: High Traffic
        high_state = low_state.copy()
        high_state["lane_counts"]["north"] = 25 # High count
        resp_high = requests.post(f"{BASE_URL}/signal/decision", json=high_state).json()
        duration_high = resp_high["recommended_duration"]
        
        print(f"Low Traffic Duration: {duration_low}s | High Traffic Duration: {duration_high}s")
        self.assertGreater(duration_high, duration_low, "AI should increase duration for heavier traffic.")
        self.assertLessEqual(duration_high, 30.0, "AI must not exceed MAX_GREEN (30s).")

    def test_yellow_phase_logging(self):
        """Verify that signal phases are correctly logged in the DB."""
        # Log a manual phase
        requests.post(f"{BASE_URL}/simulation/log", json={
            "session_id": self.session_id,
            "lane": "north",
            "duration": 15.5
        })
        
        # Retrieve report
        report = requests.get(f"{BASE_URL}/simulation/results/{self.session_id}").json()
        logs = report.get("actual_signal_log", [])
        
        self.assertTrue(any(l['lane'] == 'north' and l['duration'] == 15.5 for l in logs), 
                        "Signal phase should be recorded in actual_signal_log.")

if __name__ == "__main__":
    unittest.main()
