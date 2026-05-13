"""
Groq LLM Integration Test
"""
import requests
import unittest

BASE_URL = "http://localhost:8000"

class TestGroq(unittest.TestCase):
    def test_llm_explanation(self):
        print("Testing LLM Explanation (Groq)...")
        payload = {
            "lane_counts": {"north": 10, "south": 2, "east": 1, "west": 1},
            "wait_times": {"north": 30, "south": 5, "east": 5, "west": 5},
            "ambulance": {"north": False, "south": False, "east": False, "west": False},
            "current_lane": "north",
            "decision_made": 20.0
        }
        resp = requests.post(f"{BASE_URL}/signal/explain", json=payload)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("explanation", resp.json())
        print(f"AI Response: {resp.json()['explanation'][:50]}...")

if __name__ == "__main__":
    unittest.main()
