from backend.database.db import get_connection  # DB connection

# Get simulation results for a session

def get_simulation_results(session_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT system_type, avg_wait_time, total_vehicles_crossed, co2_estimate, avg_green_utilization, ambulance_avg_wait_time FROM simulation_result WHERE session_id = ?", (session_id,))
    rows = cursor.fetchall()
    conn.close()
    dynamic_row = None
    static_row = None
    for row in rows:
        result = {
            "avg_wait_time": row[1],
            "total_vehicles_crossed": row[2],
            "co2_estimate": row[3],
            "avg_green_utilization": row[4],
            "ambulance_avg_wait_time": row[5]
        }
        if row[0] == "dynamic":
            dynamic_row = result
        elif row[0] == "static":
            static_row = result
    if not dynamic_row or not static_row:
        return {"error": "Results not found"}
    return {"dynamic": dynamic_row, "static": static_row}

# Format comparison result

def format_comparison(session_id, dynamic_row, static_row):
    return {
        "sessionId": session_id,
        "dynamic": dynamic_row,
        "static": static_row
    }
