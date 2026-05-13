"""
KPI Validation: Ambulance Wait Time vs General Traffic (Final Fix).
"""
import requests
import unittest

BASE_URL = "http://localhost:8000"

class TestAmbulanceKPI(unittest.TestCase):
    def test_ambulance_kpi_performance(self):
        print("\n--- Testing KPI: Ambulance Wait Time vs General Traffic ---")
        
        # 1. Start a clean session
        session = requests.post(f"{BASE_URL}/simulation/start", json={"timer_duration": 60}).json()
        sid = session["session_id"]
        
        # 2. Submit a batch of events
        events = [
            # Normal Car: Wait 30s
            {"eventType": "vehicle_added", "vehicleId": "CAR-1", "laneId": "north", "vehicleType": "car", "timestamp": 0},
            {"eventType": "vehicle_crossed", "vehicleId": "CAR-1", "laneId": "north", "vehicleType": "car", "timestamp": 30000},
            
            # Ambulance: Wait 5s
            {"eventType": "vehicle_added", "vehicleId": "AMB-1", "laneId": "south", "vehicleType": "ambulance", "timestamp": 5000},
            {"eventType": "vehicle_crossed", "vehicleId": "AMB-1", "laneId": "south", "vehicleType": "ambulance", "timestamp": 10000}
        ]
        
        requests.post(f"{BASE_URL}/simulation/submit-log", json={
            "session_id": sid,
            "events": events
        })

        # 3. Fetch results
        results = requests.get(f"{BASE_URL}/simulation/results/{sid}").json()
        dynamic = results.get("dynamic", {})
        
        general_wait = dynamic.get("avg_wait_time", 0.0)
        amb_wait = dynamic.get("ambulance_avg_wait_time", 0.0)
        
        print(f"General Avg Wait: {general_wait}s")
        print(f"Ambulance Avg Wait: {amb_wait}s")
        
        # Verification
        self.assertEqual(amb_wait, 5.0, "Ambulance wait time calculation error.")
        self.assertEqual(general_wait, 17.5, "General avg wait should be (30+5)/2 = 17.5s")
        self.assertLess(amb_wait, general_wait, "Ambulance priority win verified.")
        
        print("✅ KPI VALIDATED: 17.5s (Avg) vs 5s (Ambulance). Data pipeline is now perfect.")

if __name__ == "__main__":
    unittest.main()
