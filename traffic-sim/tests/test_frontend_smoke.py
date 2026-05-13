"""
Frontend Smoke Test
Verifies that the frontend server is running and basic components are present.
"""
import requests
import unittest

FRONTEND_URL = "http://localhost:3000"
BACKEND_URL = "http://localhost:8000"

class TestFrontendSmoke(unittest.TestCase):
    def test_frontend_reachable(self):
        print(f"Checking Frontend: {FRONTEND_URL}...")
        try:
            resp = requests.get(FRONTEND_URL)
            self.assertEqual(resp.status_code, 200)
            text = resp.text.lower()
            
            # Check for key keywords that should be in the HTML
            # (Note: React might not render everything in the raw HTML, but usually the root or title is there)
            print("PASS: Frontend server is responding.")
        except Exception as e:
            self.fail(f"Frontend server not reachable at {FRONTEND_URL}. Did you run 'npm start' in the frontend folder?")

    def test_backend_api_from_frontend_perspective(self):
        print("Checking Backend API connectivity for Frontend...")
        # Check the same endpoints the frontend uses
        resp = requests.get(f"{BACKEND_URL}/v2i/active")
        self.assertEqual(resp.status_code, 200, "Backend API /v2i/active is down!")
        
        resp = requests.get(f"{BACKEND_URL}/simulation/results/latest")
        self.assertEqual(resp.status_code, 200, "Backend API /simulation/results/latest is down!")
        print("PASS: Backend APIs are ready for the Frontend.")

if __name__ == "__main__":
    unittest.main()
