from backend.database.db import get_connection  # DB connection
import json
from backend.services.static_replay_service import compute_static_metrics, compute_dynamic_metrics, compute_ambulance_wait_time_from_decisions


results_store = {}

DEFAULT_RESULT_METRICS = {
    'avg_wait_time': 0.0,
    'total_vehicles_crossed': 0.0,
    'co2_estimate': 0.0,
    'avg_green_utilization': 0.0,
    'ambulance_avg_wait_time': 0.0,
}


def _vehicle_crossed_events(events):
    vehicle_crossed_events = [
        e for e in (events or [])
        if isinstance(e, dict) and (
            e.get("eventType") == "vehicle_crossed"
            or e.get("event_type") == "vehicle_crossed"
        )
    ]
    print("TOTAL EVENTS:", len(events or []))
    print("CROSSED EVENTS:", len(vehicle_crossed_events))
    print("FIRST 3 EVENTS:", (events or [])[:3])
    return vehicle_crossed_events


def _safe_lane_state(lane_state):
    if not isinstance(lane_state, dict):
        lane_state = {}
    return {
        'north': lane_state.get('north', 0) or 0,
        'south': lane_state.get('south', 0) or 0,
        'east': lane_state.get('east', 0) or 0,
        'west': lane_state.get('west', 0) or 0,
    }


def _safe_result(result):
    if result is None or not isinstance(result, dict):
        result = {}
    lane_state = _safe_lane_state(result.get('lane_state'))
    return {
        **DEFAULT_RESULT_METRICS,
        **result,
        'avg_wait_time': float(result.get('avg_wait_time') or 0.0),
        'total_vehicles_crossed': float(result.get('total_vehicles_crossed') or 0.0),
        'co2_estimate': float(result.get('co2_estimate') or 0.0),
        'avg_green_utilization': float(result.get('avg_green_utilization') or 0.0),
        'ambulance_avg_wait_time': float(result.get('ambulance_avg_wait_time') or 0.0),
        'lane_state': lane_state,
    }


def cache_simulation_results(session_id, dynamic_row, static_row):
    session_id = str(session_id).strip() if session_id is not None else None
    if not session_id:
        return
    results_store[session_id] = {
        "dynamic": _safe_result(dynamic_row),
        "static": _safe_result(static_row),
    }


def _aggregate_live_snapshot_metrics(session_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT payload
        FROM simulation_event
        WHERE session_id = ? AND event_type = 'rl_decision'
        ORDER BY id ASC
        """,
        (session_id,),
    )
    rows = cursor.fetchall()
    conn.close()

    total_wait = 0.0
    total_queue = 0.0
    max_queue = 0
    num_decisions = 0
    latest_lane_state = {'north': 0, 'south': 0, 'east': 0, 'west': 0}

    for row in rows:
        payload_raw = row[0] if row else None
        if not payload_raw:
            continue
        try:
            payload = json.loads(payload_raw)
        except Exception:
            continue

        snapshot = payload.get('snapshot', {}) if isinstance(payload, dict) else {}
        if not isinstance(snapshot, dict):
            continue

        wait_times_raw = snapshot.get('wait_time_by_direction', {})
        queues_raw = snapshot.get('queue_length_by_direction', {})
        lane_state_raw = snapshot.get('lane_state', {})

        wait_times = {
            direction: float((wait_times_raw or {}).get(direction, 0.0) or 0.0)
            for direction in ('north', 'south', 'east', 'west')
        }
        queues = {
            direction: int((queues_raw or {}).get(direction, 0) or 0)
            for direction in ('north', 'south', 'east', 'west')
        }

        latest_lane_state = {
            direction: int(((lane_state_raw or {}).get(direction) or {}).get('count', 0) or 0)
            for direction in ('north', 'south', 'east', 'west')
        }

        total_wait += sum(wait_times.values())
        total_queue += sum(queues.values())
        max_queue = max(max_queue, max(queues.values()) if queues else 0)
        num_decisions += 1

    if num_decisions <= 0:
        return None

    avg_wait = (total_wait / num_decisions) / 4.0
    print("DASHBOARD METRICS:", avg_wait, total_queue)
    events = get_events_for_session(session_id)
    vehicle_crossed_events = _vehicle_crossed_events(events)
    total_vehicles_crossed = len(vehicle_crossed_events)

    ambulance_wait = compute_ambulance_wait_time_from_decisions(events)

    return {
        'avg_wait_time': float(avg_wait),
        'total_vehicles_crossed': total_vehicles_crossed,
        'co2_estimate': float(avg_wait * 2.3),
        'avg_green_utilization': 100.0 if total_queue > 0 else 0.0,
        'ambulance_avg_wait_time': ambulance_wait,
        'max_queue_length': int(max_queue),
        'lane_state': latest_lane_state,
    }


def get_events_for_session(session_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT timestamp, event_type, lane_id, vehicle_type, vehicle_id, payload
        FROM simulation_event
        WHERE session_id = ?
        ORDER BY id ASC
        """,
        (session_id,),
    )
    rows = cursor.fetchall()
    conn.close()

    events = []
    for row in rows:
        payload_raw = row[5] if row else None
        payload = {}
        if payload_raw:
            try:
                payload = json.loads(payload_raw)
            except Exception:
                payload = {}

        events.append({
            'timestamp': row[0],
            'eventType': row[1],
            'laneId': row[2],
            'vehicleType': row[3],
            'vehicleId': row[4],
            'payload': payload,
        })

    return events


def get_decision_logs(session_id):
    import json
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT tick_number, timestamp, selected_lane, duration, strategy, snapshot, decision_debug
        FROM simulation_decision_log
        WHERE session_id = ?
        ORDER BY timestamp ASC
        """,
        (session_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    logs = []
    for row in rows:
        logs.append({
            "tick": row[0],
            "timestamp": row[1],
            "selected_lane": row[2],
            "duration": row[3],
            "strategy": row[4],
            "snapshot": json.loads(row[5]) if row[5] else {},
            "debug": json.loads(row[6]) if row[6] else {}
        })
    return logs


def build_phase_history(decisions):
    if not decisions:
        return []

    phase_history = []

    def normalize_lane(value):
        lane = str(value or "").strip().upper()
        return lane if lane else "--"

    def normalize_duration(value):
        try:
            duration = float(value)
        except (TypeError, ValueError):
            duration = 0.0
        return duration

    def normalize_tick(value, fallback):
        try:
            tick = int(value)
        except (TypeError, ValueError):
            tick = fallback
        return tick

    first = decisions[0] or {}
    current_lane = normalize_lane(first.get("selected_lane") or first.get("lane"))
    total_duration = normalize_duration(first.get("duration"))
    start_tick = normalize_tick(first.get("tick"), 1)
    end_tick = start_tick

    for index, decision in enumerate(decisions[1:], start=2):
        entry = decision or {}
        lane = normalize_lane(entry.get("selected_lane") or entry.get("lane"))
        duration = normalize_duration(entry.get("duration"))
        tick = normalize_tick(entry.get("tick"), index)

        if lane == current_lane:
            total_duration += duration
            end_tick = tick
            continue

        phase_history.append({
            "lane": current_lane,
            "duration": total_duration,
            "start_tick": start_tick,
            "end_tick": end_tick,
        })

        current_lane = lane
        total_duration = duration
        start_tick = tick
        end_tick = tick

    phase_history.append({
        "lane": current_lane,
        "duration": total_duration,
        "start_tick": start_tick,
        "end_tick": end_tick,
    })
    return phase_history


def _build_phase_history(session_id):
    logs = get_decision_logs(session_id)
    return build_phase_history(logs)


def _build_raw_signal_log(session_id):
    simulation_log = get_decision_logs(session_id)
    raw_signal_log = []

    for row in simulation_log:
        raw_signal_log.append({
            "lane": row.get("selected_lane") or row.get("lane"),
            "duration": row.get("duration"),
        })

    return raw_signal_log


def _build_actual_signal_summary(session_id):
    simulation_log = get_decision_logs(session_id)
    lane_totals = {
        "north": 0.0,
        "south": 0.0,
        "east": 0.0,
        "west": 0.0,
    }

    for row in simulation_log:
        lane = str((row.get("selected_lane") or row.get("lane") or "")).lower()
        try:
            duration = float(row.get("duration", 0) or 0)
        except (TypeError, ValueError):
            duration = 0.0

        if lane in lane_totals:
            lane_totals[lane] += duration

    actual_signal_summary = [
        {"lane": lane, "duration": duration}
        for lane, duration in lane_totals.items()
    ]
    return actual_signal_summary


def _build_actual_signal_log(session_id):
    simulation_log = get_decision_logs(session_id)
    return [
        {
            "lane": row.get("selected_lane") or row.get("lane"),
            "duration": row.get("duration"),
        }
        for row in simulation_log
    ]

# Get simulation results for a session

def get_simulation_results(session_id):
    session_id = str(session_id).strip() if session_id is not None else None
    if not session_id:
        return {"error": "Results not found"}

    events = get_events_for_session(session_id)
    if events:
        # Pass timer_duration as None, function will infer it from timestamps
        dynamic_metrics = compute_dynamic_metrics(events, None)
        dynamic_result = _safe_result(dynamic_metrics)
        
        static_metrics = compute_static_metrics(events)
        static_result = _safe_result(static_metrics)
        
        return {
            'dynamic': dynamic_result,
            'static': static_result,
            'actual_signal_log': _build_actual_signal_log(session_id),
        }

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
    if not dynamic_row and not static_row:
        return {"error": "Results not found", "dynamic": _safe_result(None), "static": _safe_result(None)}

    if not dynamic_row and static_row:
        dynamic_row = static_row.copy()
    if not static_row and dynamic_row:
        static_row = dynamic_row.copy()

    dynamic_row = _safe_result(dynamic_row)
    static_row = _safe_result(static_row)

    results_store[session_id] = {
        "dynamic": dynamic_row,
        "static": static_row,
    }
    return {
        "dynamic": dynamic_row,
        "static": static_row,
        "actual_signal_log": _build_actual_signal_log(session_id),
    }


def get_session_metrics_for_dashboard(session_id):
    return get_simulation_results(session_id)

# Format comparison result

def format_comparison(session_id, dynamic_row, static_row, actual_signal_log=None):
    dynamic_row = _safe_result(dynamic_row)
    static_row = _safe_result(static_row)
    lower_is_better = {'avg_wait_time', 'co2_estimate', 'ambulance_avg_wait_time'}
    higher_is_better = {'total_vehicles_crossed', 'avg_green_utilization'}
    metric_keys = lower_is_better.union(higher_is_better)

    def get_winner(metric_key, dynamic_value, static_value):
        if dynamic_value is None or static_value is None:
            return 'n/a'
        if metric_key in lower_is_better:
            if dynamic_value < static_value:
                return 'dynamic'
            if static_value < dynamic_value:
                return 'static'
            return 'tie'
        if metric_key in higher_is_better:
            if dynamic_value > static_value:
                return 'dynamic'
            if static_value > dynamic_value:
                return 'static'
            return 'tie'
        return 'n/a'

    def get_uplift_pct(metric_key, dynamic_value, static_value):
        if dynamic_value is None or static_value in (None, 0):
            return None
        if metric_key in lower_is_better:
            return ((static_value - dynamic_value) / static_value) * 100.0
        if metric_key in higher_is_better:
            return ((dynamic_value - static_value) / static_value) * 100.0
        return None

    wins = {'dynamic': 0, 'static': 0, 'tie': 0, 'n/a': 0}
    uplift = {}
    for metric_key in metric_keys:
        winner = get_winner(metric_key, dynamic_row.get(metric_key), static_row.get(metric_key))
        wins[winner] = wins.get(winner, 0) + 1
        uplift[metric_key] = {
            'winner': winner,
            'uplift_pct': get_uplift_pct(metric_key, dynamic_row.get(metric_key), static_row.get(metric_key))
        }

    return {
        "sessionId": session_id,
        "dynamic": dynamic_row,
        "static": static_row,
        "actual_signal_log": actual_signal_log if isinstance(actual_signal_log, list) else [],
        "benchmark": {
            "wins": wins,
            "uplift": uplift
        }
    }
