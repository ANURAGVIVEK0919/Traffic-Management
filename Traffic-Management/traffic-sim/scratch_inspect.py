import sqlite3
import json

def inspect():
    conn = sqlite3.connect('traffic_sim.db')
    cursor = conn.cursor()
    
    session_id = '8c1d9c0c-b589-4359-8833-9edbfcef610b'
    
    print("--- Session Details ---")
    cursor.execute("SELECT * FROM simulation_session WHERE id = ?", (session_id,))
    print("Session:", cursor.fetchall())
    
    print("\n--- Simulation Results ---")
    cursor.execute("SELECT * FROM simulation_result WHERE session_id = ?", (session_id,))
    results = cursor.fetchall()
    for row in results:
        print(row)
        
    print("\n--- Event Statistics ---")
    cursor.execute("SELECT event_type, COUNT(*) FROM simulation_event WHERE session_id = ? GROUP BY event_type", (session_id,))
    print("Events count:", cursor.fetchall())
    
    print("\n--- All Vehicles Injected ---")
    cursor.execute("SELECT DISTINCT vehicle_id, vehicle_type, lane_id FROM simulation_event WHERE session_id = ? AND event_type = 'vehicle_added'", (session_id,))
    vehicles = cursor.fetchall()
    print(f"Total vehicle_added events: {len(vehicles)}")
    for v in vehicles[:20]:
        print(v)
        
    print("\n--- Emergency Vehicles ---")
    cursor.execute("SELECT DISTINCT vehicle_id, vehicle_type, lane_id FROM simulation_event WHERE session_id = ? AND (vehicle_id LIKE '%v2i%' OR vehicle_type LIKE '%ambulance%')", (session_id,))
    emergency = cursor.fetchall()
    print("Emergency vehicles found:", emergency)
    
    conn.close()

if __name__ == '__main__':
    inspect()
