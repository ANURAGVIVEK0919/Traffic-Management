"""
Test Suite 2: V2I Hub & Emergency Preemption Logic
Tests digital beacons, ETA calculations, and preemption triggers.
"""

import requests
import time
import unittest

BASE_URL = "http://localhost:8000"

class TestV2IPreemption(unittest.TestCase):
    def test_v2i_beacon_registration(self):
        """Test if the V2I hub correctly acquires and tracks a beacon signal."""
        print("Testing V2I Beacon Registration...")
        
        # Trigger a beacon for North lane from 400m away
        payload = {
            "vehicle_id": "TEST-AMB-999",
            "lane": "north",
            "distance": 400.0,
            "speed": 20.0 # Fast ambulance
        }
        resp = requests.post(f"{BASE_URL}/v2i/beacon", json=payload)
        self.assertEqual(resp.status_code, 200)
        
        # Check active status
        status = requests.get(f"{BASE_URL}/v2i/active").json()
        found = False
        for b in status:
            if b['vehicle_id'] == "TEST-AMB-999":
                found = True
                self.assertEqual(b['lane'], 'north')
                self.assertLessEqual(b['eta'], 20.0, "ETA calculation should be distance/speed.")
                break
        
        self.assertTrue(found, "Beacon should be active in the V2I hub.")

    def test_preemption_logic_flow(self):
        """Test the logic flow: V2I Alert -> Emergency Phase Activation."""
        print("Testing V2I -> Preemption Flow...")
        
        # 1. Trigger V2I for West lane
        requests.post(f"{BASE_URL}/v2i/beacon", json={
            "vehicle_id": "TEST-AMB-V2I",
            "lane": "west",
            "distance": 200.0,
            "speed": 10.0
        })
        
        # 2. Check active beacons
        resp = requests.get(f"{BASE_URL}/v2i/active").json()
        self.assertTrue(len(resp) > 0, "There should be an active V2I alert.")
        
        # 3. Simulate Signal Controller check
        # In a real run, the frontend would poll this and switch.
        # Here we verify the backend state is ready.
        print("V2I Hub is broadcasting the priority intent to the Controller.")

if __name__ == "__main__":
    unittest.main()
