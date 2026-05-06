"""
Groq LLM Integration Test

Verifies:
1. Decision explanation (Reasoning)
2. Command parsing (Configuration)
3. API Latency & Connectivity
"""

import requests
import json
import time

BASE_URL = "http://localhost:8000"

def run_groq_test():
    print("\n🧠 Starting Groq AI (Llama 3.3) Integration Test...")
    print("="*70)

    # 🧪 TEST 1: Decision Explanation
    print("\n[TEST 1] Decision Explanation (Reasoning)")
    traffic_state = {
        "lane_counts": {"north": 15, "south": 2, "east": 1, "west": 1},
        "wait_times": {"north": 45.5, "south": 5.0, "east": 2.0, "west": 2.0},
        "ambulance": {"north": False, "south": False, "east": False, "west": False},
        "current_lane": "north",
        "decision_made": 25.0
    }
    
    start_time = time.time()
    try:
        resp = requests.post(f"{BASE_URL}/signal/explain", json=traffic_state)
        latency = time.time() - start_time
        data = resp.json()
        explanation = data.get("explanation", "")
        
        print(f"🕒 Latency: {latency:.2f}s")
        print(f"💬 AI Explanation: \"{explanation}\"")
        
        if "North" in explanation or "15" in explanation or "wait" in explanation.lower():
            print("✅ Verification: AI is correctly referencing traffic data in its reasoning.")
        else:
            print("⚠️ Warning: AI explanation seems generic or is using fallback.")
            
    except Exception as e:
        print(f"❌ Error during explanation test: {e}")

    # 🧪 TEST 2: Natural Language Configuration
    print("\n[TEST 2] Natural Language Configuration (Parsing)")
    commands = [
        "give ambulances highest priority immediately",
        "set the yellow phase duration to 7 seconds",
        "increase max green time to 28 seconds for heavy traffic"
    ]
    
    for cmd in commands:
        print(f"\n👉 Command: \"{cmd}\"")
        try:
            resp = requests.post(f"{BASE_URL}/signal/configure", json={"command": cmd})
            data = resp.json()
            print(f"🤖 AI Acknowledgment: \"{data['acknowledged']}\"")
            print(f"📦 Parsed Params: {data['params']}")
            
            if data['params']:
                print("✅ Verification: Successfully parsed into structured data.")
            else:
                print("❌ Verification: Failed to extract parameters.")
        except Exception as e:
            print(f"❌ Error during config test: {e}")

    print("\n" + "="*70)
    print("🏆 Groq AI Integration Test Complete!")

if __name__ == "__main__":
    run_groq_test()
