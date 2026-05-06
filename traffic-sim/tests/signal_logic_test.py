"""
Signal Logic & Phase Transition Test

Verifies:
1. Ambulance Priority (Current vs Waiting Lane)
2. Green Extension (High vs Low Density)
3. Yellow Phase configuration via LLM
"""

import requests
import json

BASE_URL = "http://localhost:8000"

def run_logic_test():
    print("\n🚦 Starting Signal Logic & Phase Transition Test...")
    print("="*70)

    # TEST 1: Ambulance Priority (Current Lane)
    print("\n[TEST 1] Ambulance in Current Lane (Should get high duration)")
    state_amb_current = {
        "lane_counts": {"north": 10, "south": 2, "east": 2, "west": 2},
        "wait_times": {"north": 5.0, "south": 0.0, "east": 0.0, "west": 0.0},
        "ambulance": {"north": True, "south": False, "east": False, "west": False},
        "current_lane": "north"
    }
    resp = requests.post(f"{BASE_URL}/signal/decision", json=state_amb_current).json()
    dur_amb = resp["recommended_duration"]
    print(f"✅ Recommended Duration: {dur_amb}s")

    # TEST 2: Ambulance Priority (Waiting Lane)
    print("\n[TEST 2] Ambulance in Waiting Lane (Current should be shorter to switch)")
    state_amb_waiting = {
        "lane_counts": {"north": 10, "south": 2, "east": 2, "west": 2},
        "wait_times": {"north": 5.0, "south": 0.0, "east": 0.0, "west": 0.0},
        "ambulance": {"north": False, "south": True, "east": False, "west": False},
        "current_lane": "north"
    }
    resp = requests.post(f"{BASE_URL}/signal/decision", json=state_amb_waiting).json()
    dur_waiting = resp["recommended_duration"]
    print(f"✅ Recommended Duration: {dur_waiting}s")
    
    if dur_amb >= dur_waiting:
        print("📊 Verification: AI correctly prioritizes lane with Ambulance.")
    else:
        print("⚠️ Warning: Model behavior inconsistent for ambulance priority.")

    # TEST 3: Green Extension (High vs Low Density)
    print("\n[TEST 3] Green Extension (Heavy vs Light Traffic)")
    state_heavy = {"lane_counts": {"north": 20, "south": 0, "east": 0, "west": 0}, "current_lane": "north"}
    state_light = {"lane_counts": {"north": 2, "south": 0, "east": 0, "west": 0}, "current_lane": "north"}
    
    dur_heavy = requests.post(f"{BASE_URL}/signal/decision", json=state_heavy).json()["recommended_duration"]
    dur_light = requests.post(f"{BASE_URL}/signal/decision", json=state_light).json()["recommended_duration"]
    
    print(f"   - Heavy Traffic: {dur_heavy}s")
    print(f"   - Light Traffic: {dur_light}s")
    if dur_heavy >= dur_light:
        print("✅ Verification: Green extension logic is working correctly.")

    # TEST 4: Yellow Phase Configuration (LLM)
    print("\n[TEST 4] Yellow Phase Configuration via LLM")
    config_cmd = {"command": "set yellow phase to 8 seconds for emergency safety"}
    resp = requests.post(f"{BASE_URL}/signal/configure", json=config_cmd).json()
    print(f"✅ LLM Response: {resp['acknowledged']}")
    print(f"✅ Parsed Params: {resp['params']}")
    
    if 'yellow' in str(resp['params']).lower() or 'phase' in str(resp['params']).lower():
        print("📊 Verification: LLM successfully parsed the yellow phase command.")
    else:
        print("⚠️ Warning: LLM failed to structure the yellow phase parameter.")

    print("\n" + "="*70)
    print("🏆 Phase & Logic Test Complete!")

if __name__ == "__main__":
    run_logic_test()
