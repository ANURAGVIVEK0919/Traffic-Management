"""
Preemption Trace Verification Test

Verifies if the backend correctly logs and reports a sequence where:
1. North is interrupted by an Ambulance.
2. South (Ambulance) takes over.
3. North resumes to finish its cycle.
"""

import requests
import time

BASE_URL = "http://localhost:8000"

def run_preemption_trace_test():
    print("\n🚑 Starting Preemption Trace Verification...")
    print("="*70)

    # 1. Start a session
    resp = requests.post(f"{BASE_URL}/simulation/start", json={"timer_duration": 120}).json()
    session_id = resp["session_id"]
    print(f"✅ Session Started: {session_id}")

    # 2. Log Phase 1: North (Interrupted at 10s)
    print("🎬 Logging Phase 1: North (Interrupted at 10s)")
    requests.post(f"{BASE_URL}/simulation/log", json={
        "session_id": session_id,
        "lane": "north",
        "duration": 10.0
    })

    # 3. Log Phase 2: South (Ambulance Priority - 8s)
    print("🚑 Logging Phase 2: South (Ambulance Priority - 8s)")
    requests.post(f"{BASE_URL}/simulation/log", json={
        "session_id": session_id,
        "lane": "south",
        "duration": 8.0
    })

    # 4. Log Phase 3: North (Resumed for 5s)
    print("🔄 Logging Phase 3: North (Resumed for 5s)")
    requests.post(f"{BASE_URL}/simulation/log", json={
        "session_id": session_id,
        "lane": "north",
        "duration": 5.0
    })

    # 5. Submit one mock event so metrics are computed and results object is created
    print("📊 Submitting mock state sync event...")
    requests.post(f"{BASE_URL}/simulation/submit-log", json={
        "session_id": session_id,
        "events": [{"eventType": "state_sync", "timestamp": time.time()*1000, "payload": {}}]
    })

    # 6. Verify the report
    print("\n📊 Verifying Final Report...")
    report = requests.get(f"{BASE_URL}/simulation/report/{session_id}").json()
    
    # Check results safely
    results = report.get("results")
    if not results:
        # If results is None, try fetching signal logs directly via another endpoint
        print("⚠️ Results object missing in report. Fetching raw logs...")
        resp = requests.get(f"{BASE_URL}/simulation/results/{session_id}").json()
        signal_log = resp.get("actual_signal_log", [])
    else:
        signal_log = results.get("actual_signal_log", [])
    
    print("\nCaptured Signal Sequence:")
    for i, phase in enumerate(signal_log):
        print(f"   {i+1}. Lane: {phase['lane']:<6} | Duration: {phase['duration']}s")

    # Validation
    if len(signal_log) >= 3:
        lanes = [p['lane'] for p in signal_log]
        if lanes[0] == 'north' and lanes[1] == 'south' and lanes[2] == 'north':
            print("\n✅ SUCCESS: Backend correctly logged the Interrupted -> Ambulance -> Resumed sequence!")
        else:
            print(f"\n⚠️ Sequence Mismatch: Expected [north, south, north], got {lanes}")
    else:
        print(f"\n❌ Failed: Expected at least 3 phases, found {len(signal_log)}")

    print("="*70)

if __name__ == "__main__":
    run_preemption_trace_test()
