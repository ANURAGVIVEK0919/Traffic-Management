import os
import torch
import sys

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def test_model_loading():
    print("--- 🤖 AI Model Test ---")
    model_path = "models/dqn_indian_traffic_final.pth"
    if os.path.exists(model_path):
        try:
            state = torch.load(model_path, map_location='cpu', weights_only=True)
            print(f"✅ DQN Model found and loadable! ({model_path})")
            print(f"Model keys: {list(state.keys())[:5]}... total {len(state)} keys.")
        except Exception as e:
            print(f"❌ Error loading model: {e}")
    else:
        print(f"❌ Model NOT found at {model_path}")

def test_db_tables():
    print("\n--- 📊 Database Test ---")
    import sqlite3
    try:
        conn = sqlite3.connect("traffic_sim.db")
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        print(f"✅ Found tables: {tables}")
        
        required = ['video_detections_cache', 'video_events_cache', 'simulation_decision_log']
        for r in required:
            if r in tables:
                print(f"   - {r}: OK")
            else:
                print(f"   - {r}: MISSING")
        conn.close()
    except Exception as e:
        print(f"❌ DB Error: {e}")

if __name__ == "__main__":
    test_model_loading()
    test_db_tables()
