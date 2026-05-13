import sqlite3
import os

# Correct path: root of traffic-sim
db_path = r"e:\Traffic Managment\Traffic-Management\traffic-sim\traffic_sim.db"

def check_metrics():
    if not os.path.exists(db_path):
        print("DB not found at:", db_path)
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("--- LATEST SIMULATION RESULTS ---")
    try:
        cursor.execute("""
            SELECT session_id, system_type, avg_wait_time, co2_estimate 
            FROM simulation_result 
            ORDER BY created_at DESC LIMIT 10
        """)
        rows = cursor.fetchall()
        
        if not rows:
            print("No results found in simulation_result table yet.")
        else:
            for row in rows:
                print(f"Session: {row[0][:8]}... | Mode: {row[1]:7} | Wait: {row[2]:.2f}s | CO2: {row[3]:.2f}")
    except Exception as e:
        print("Error reading table:", e)
    
    conn.close()

if __name__ == "__main__":
    check_metrics()
