"""Diagnose POST /simulation/submit-log with multiple payload shapes.

Run from the backend folder:
    python test_submit_log.py
"""

from __future__ import annotations

import traceback
import uuid

import requests


BASE_URL = "http://localhost:8000"
ENDPOINT = f"{BASE_URL}/simulation/submit-log"


def test_payload(name, payload):
    print(f"===== TEST: {name} =====")
    try:
        response = requests.post(ENDPOINT, json=payload, timeout=5)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")
        if response.status_code != 200:
            print("❌ FAILED")
            return False
        return True
    except Exception as exc:
        print(f"Exception: {exc}")
        traceback.print_exc()
        print("❌ FAILED")
        return False


def build_cases(session_id):
    return [
        (
            "Minimal valid payload",
            {
                "session_id": session_id,
                "events": [
                    {
                        "lane": "north",
                        "vehicle_count": 1,
                        "waitTime": 5,
                        "timestamp": 1,
                    }
                ],
            },
        ),
        (
            "Empty events",
            {
                "session_id": session_id,
                "events": [],
            },
        ),
        (
            "None events",
            {
                "session_id": session_id,
                "events": None,
            },
        ),
        (
            "Missing fields",
            {
                "session_id": session_id,
                "events": [{}],
            },
        ),
        (
            "Invalid types",
            {
                "session_id": session_id,
                "events": [
                    {
                        "lane": 123,
                        "vehicle_count": "bad",
                        "waitTime": None,
                    }
                ],
            },
        ),
        (
            "Large valid payload",
            {
                "session_id": session_id,
                "events": [
                    {
                        "lane": "north",
                        "vehicle_count": 3,
                        "waitTime": 10,
                        "timestamp": i,
                    }
                    for i in range(10)
                ],
            },
        ),
    ]


def main():
    session_id = str(uuid.uuid4())
    print(f"Generated session_id: {session_id}")

    cases = build_cases(session_id)
    passed = []
    failed = []

    for name, payload in cases:
        ok = test_payload(name, payload)
        if ok:
            passed.append(name)
        else:
            failed.append(name)
        print()

    print("===== SUMMARY =====")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")


if __name__ == "__main__":
    main()