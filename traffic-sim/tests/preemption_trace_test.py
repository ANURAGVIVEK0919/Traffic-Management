"""
Preemption Trace Test — Verifies the sequence of signal logs.
"""
import requests
import time
import unittest

BASE_URL = "http://localhost:8000"

class TestPreemptionTrace(unittest.TestCase):
    def test_log_sequence(self):
        print("Testing Signal Log Trace...")
        # 1. Start Session
        resp = requests.post(f"{BASE_URL}/simulation/start", json={"timer_duration": 60}).json()
        sid = resp["session_id"]
        
        # 2. Log Interrupted Phase (North)
        requests.post(f"{BASE_URL}/simulation/log", json={"session_id": sid, "lane": "north", "duration": 10.0})
        # 3. Log Ambulance Phase (South)
        requests.post(f"{BASE_URL}/simulation/log", json={"session_id": sid, "lane": "south", "duration": 8.0})
        # 4. Log Resumed Phase (North)
        requests.post(f"{BASE_URL}/simulation/log", json={"session_id": sid, "lane": "north", "duration": 5.0})
        
        # 5. Verify Report
        report = requests.get(f"{BASE_URL}/simulation/results/{sid}").json()
        logs = report.get("actual_signal_log", [])
        
        lanes = [l['lane'] for l in logs]
        print(f"Captured Sequence: {lanes}")
        self.assertEqual(lanes, ["north", "south", "north"], "Sequence should be North -> South -> North")

if __name__ == "__main__":
    unittest.main()
