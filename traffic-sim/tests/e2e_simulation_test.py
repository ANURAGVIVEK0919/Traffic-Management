"""
End-to-End Simulation Integration Test

This script simulates a complete traffic session:
1. Creates a session
2. Sends multiple traffic states to the Neural Net for decisions
3. Logs signal phases and events
4. Fetches and validates the final report (Dashboard data)
"""

import requests
import time
import random

BASE_URL = "http://localhost:8000"

def run_e2e_test():
    print("🚀 Starting End-to-End Simulation Test...")

    # 1. Create a Session
    print("\n[1/4] Creating Session...")
    try:
        # Correct path: /simulation/start, Correct field: timer_duration
        resp = requests.post(f"{BASE_URL}/simulation/start", json={"timer_duration": 60})
        resp.raise_for_status()
        session_id = resp.json()["session_id"]
        print(f"✅ Session Created: {session_id}")
    except Exception as e:
        print(f"❌ Failed to create session: {e}")
        return

    # 2. Test Signal Decisions (Neural Net)
    print("\n[2/4] Testing AI Decisions (Neural Net)...")
    lanes = ["north", "east", "south", "west"]
    for lane in lanes:
        payload = {
            "lane_counts": {l: random.randint(0, 15) for l in lanes},
            "wait_times": {l: random.uniform(0, 40) for l in lanes},
            "ambulance": {l: (l == "north" and random.random() > 0.8) for l in lanes},
            "current_lane": lane,
            "elapsed_time": random.randint(5, 25)
        }
        resp = requests.post(f"{BASE_URL}/signal/decision", json=payload)
        decision = resp.json()["recommended_duration"]
        print(f"   - Lane {lane.upper()}: Model recommended {decision:.1f}s")

    # 3. Log Fake Traffic Data
    print("\n[3/4] Logging Traffic Events (Simulation Feed)...")
    for i in range(10):
        lane = random.choice(lanes)
        vehicle_id = f"test-veh-{i}"
        vehicle_type = random.choice(["car", "bus", "ambulance"])
        
        # 3a. Add a vehicle
        add_event = {
            "eventType": "vehicle_added",
            "vehicleId": vehicle_id,
            "laneId": lane,
            "vehicleType": vehicle_type,
            "timestamp": time.time() * 1000 - 5000 # Arrived 5s ago
        }
        
        # 3b. Vehicle crosses (3s later)
        cross_event = {
            "eventType": "vehicle_crossed",
            "vehicleId": vehicle_id,
            "laneId": lane,
            "vehicleType": vehicle_type,
            "timestamp": time.time() * 1000 - 2000 # Crossed 2s ago
        }

        # Submit logs
        requests.post(f"{BASE_URL}/simulation/submit-log", json={
            "session_id": session_id,
            "events": [add_event, cross_event]
        })

        # Also log a signal phase occasionally
        if i % 2 == 0:
            requests.post(f"{BASE_URL}/simulation/log", json={
                "session_id": session_id,
                "lane": lane,
                "duration": random.uniform(10, 25)
            })
            
    print("✅ Logged 10 vehicles adding and crossing.")

    # 4. Fetch Dashboard Results
    print("\n[4/4] Fetching Dashboard Report...")
    time.sleep(1) # Small delay for DB persistence
    resp = requests.get(f"{BASE_URL}/simulation/report/{session_id}")
    report = resp.json()
    
    print("\n📊 --- TEST RESULTS (DASHBOARD SUMMARY) ---")
    # Backend uses camelCase 'sessionId'
    print(f"Session ID: {report.get('sessionId', 'N/A')}")
    
    results = report.get('results', {})
    dynamic = (results.get('dynamic') or {}) if results else {}
    
    # Extract metrics from 'dynamic' if available
    total_v = dynamic.get('total_vehicles_crossed', 0)
    avg_wait = dynamic.get('avg_wait_time', 0)
    co2 = dynamic.get('co2_estimate', 0)

    print(f"Total Vehicles Crossed: {int(total_v)}")
    print(f"Avg Wait Time: {avg_wait:.2f}s")
    print(f"CO2 Emission Estimate: {co2:.2f} kg")
    
    # Decisions info from decisionMetrics
    metrics = report.get('decisionMetrics', {})
    print(f"Total Decisions Made: {metrics.get('total_decisions', 0)}")
    
    if total_v >= 10:
        print("\n✅ E2E Test Passed! Data is flowing correctly through the AI pipeline.")
    else:
        print(f"\n⚠️ Test Warning: Expected 10 vehicles, but report shows {total_v}.")

if __name__ == "__main__":
    run_e2e_test()
