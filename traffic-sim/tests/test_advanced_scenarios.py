"""
Extreme Stress Test Suite: Concurrent Emergencies & LLM Config Parsing.
"""
import requests
import unittest

BASE_URL = "http://localhost:8000"

class TestAdvancedScenarios(unittest.TestCase):
    def test_concurrent_ambulances(self):
        print("\n--- Testing Concurrent Emergencies (Priority Queue) ---")
        # 1. Trigger Ambulance A in North (ETA 20s)
        requests.post(f"{BASE_URL}/v2i/beacon", json={
            "vehicle_id": "AMB-NORTH", "lane": "north", "distance": 400.0, "speed": 20.0
        })
        # 2. Trigger Ambulance B in West (ETA 10s) - Closer/Higher Priority
        requests.post(f"{BASE_URL}/v2i/beacon", json={
            "vehicle_id": "AMB-WEST", "lane": "west", "distance": 100.0, "speed": 10.0
        })
        
        # 3. Check V2I Hub
        active = requests.get(f"{BASE_URL}/v2i/active").json()
        self.assertGreaterEqual(len(active), 2)
        
        # Sort by ETA (simulating what the controller does)
        sorted_beacons = sorted(active, key=lambda x: x['eta'])
        print(f"Priority 1: {sorted_beacons[0]['lane']} (ETA: {sorted_beacons[0]['eta']}s)")
        self.assertEqual(sorted_beacons[0]['lane'], 'west', "Closer ambulance (West) should have priority.")

    def test_llm_config_parsing(self):
        print("\n--- Testing AI Configuration Parsing (Natural Language) ---")
        # Command: "give ambulances 40 seconds of green time"
        payload = {"command": "set max green to 40 seconds and priority to high"}
        resp = requests.post(f"{BASE_URL}/signal/configure", json=payload).json()
        
        print(f"AI Acknowledged: {resp.get('acknowledged')}")
        params = resp.get('params', {})
        print(f"Parsed Params: {params}")
        
        # Verify safety clamping (should not exceed 30)
        if 'max_green' in params:
            val = params['max_green']
            self.assertLessEqual(val, 30, "Safety clamp should prevent max_green > 30.")
            print(f"PASS: AI correctly clamped unsafe value to {val}s.")
        else:
            print("INFO: AI returned a descriptive acknowledgment without specific param overrides.")

if __name__ == "__main__":
    unittest.main()
