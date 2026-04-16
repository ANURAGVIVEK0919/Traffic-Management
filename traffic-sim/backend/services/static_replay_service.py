
from backend.utils.event_parser import parse_event_log, reconstruct_vehicle_timeline
from backend.utils.metrics import (
	compute_avg_wait_time,
	compute_total_crossed,
	compute_green_utilization,
	compute_ambulance_wait_time
)

STATIC_GREEN_DURATION = 30  # seconds per lane
CYCLE_DURATION = 120  # full cycle
LANE_ORDER = ['north', 'west', 'south', 'east']
DIRECTIONS = ('north', 'south', 'east', 'west')


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

def get_next_green_second(current_time, lane_index):
	cycle_time = current_time % CYCLE_DURATION
	green_start = lane_index * STATIC_GREEN_DURATION
	green_end = green_start + STATIC_GREEN_DURATION
	
	if green_start <= cycle_time < green_end:
		return current_time
	
	if cycle_time < green_start:
		return current_time + (green_start - cycle_time)
	else:
		return current_time + (CYCLE_DURATION - cycle_time) + green_start


def _safe_average(total, count):
	return total / count if count > 0 else 0.0


def _normalize_directional(values, cast=float):
	normalized = {}
	for direction in DIRECTIONS:
		if isinstance(values, dict):
			value = values.get(direction, 0)
		else:
			value = 0
		try:
			normalized[direction] = cast(value or 0)
		except Exception:
			normalized[direction] = cast(0)
	return normalized


def _aggregate_snapshot_wait_queue(events, debug_prefix=None):
	total_wait = 0.0
	total_queue = 0.0
	max_queue = 0
	num_decisions = 0

	for event in events or []:
		if not isinstance(event, dict):
			continue
		if event.get('eventType') != 'rl_decision':
			continue

		payload = event.get('payload', {}) or {}
		snapshot = payload.get('snapshot', {}) if isinstance(payload, dict) else {}
		if not snapshot and isinstance(event.get('snapshot'), dict):
			snapshot = event.get('snapshot')
		if not isinstance(snapshot, dict):
			continue

		wait_times = _normalize_directional(snapshot.get('wait_time_by_direction', {}), cast=float)
		queues = _normalize_directional(snapshot.get('queue_length_by_direction', {}), cast=int)

		if debug_prefix:
			print(f"{debug_prefix} WAIT SAMPLE:", wait_times)
			print(f"{debug_prefix} QUEUE SAMPLE:", queues)

		total_wait += sum(float(value) for value in wait_times.values())
		total_queue += sum(float(value) for value in queues.values())
		max_queue = max(max_queue, max(int(value) for value in queues.values()) if queues else 0)
		num_decisions += 1

	return {
		'total_wait': float(total_wait),
		'total_queue': float(total_queue),
		'max_queue': int(max_queue),
		'num_decisions': int(num_decisions),
		'avg_wait': float(_safe_average(total_wait, num_decisions)),
		'avg_queue': float(_safe_average(total_queue, num_decisions)),
	}


def _normalize_lane_id(value):
	if value is None:
		return None
	lane = str(value).strip().lower()
	return lane if lane in DIRECTIONS else None


def _normalize_signal_state(value):
	if value is None:
		return None
	return str(value).strip().upper()


def compute_ambulance_wait_time_from_decisions(events):
	decision_events = [
		e for e in (events or [])
		if isinstance(e, dict) and e.get('eventType') == 'rl_decision'
	]
	if not decision_events:
		return None

	total_wait = 0.0
	total_ambulance_observations = 0
	previous_timestamp = None

	for event in decision_events:
		payload = event.get('payload', {}) or {}
		snapshot = payload.get('snapshot', {}) if isinstance(payload, dict) else {}
		if not isinstance(snapshot, dict):
			continue

		lane_state = snapshot.get('lane_state', {})
		if not isinstance(lane_state, dict):
			continue

		current_timestamp = event.get('timestamp')
		delta_seconds = 1.0
		if previous_timestamp is not None and current_timestamp is not None:
			try:
				delta_raw = (float(current_timestamp) - float(previous_timestamp)) / 1000.0
				if delta_raw > 0:
					delta_seconds = float(delta_raw)
			except Exception:
				pass
		previous_timestamp = current_timestamp

		decision_lane = _normalize_lane_id((payload.get('decision') or {}).get('lane'))
		active_green_lane = _normalize_lane_id(snapshot.get('active_green_lane') or payload.get('active_green_lane') or decision_lane)

		for lane_id in DIRECTIONS:
			lane_data = lane_state.get(lane_id, {}) if isinstance(lane_state.get(lane_id), dict) else {}
			if not bool(lane_data.get('hasAmbulance', False)):
				continue

			total_ambulance_observations += 1
			signal_state = _normalize_signal_state(
				lane_data.get('signal_state')
				or lane_data.get('signalState')
				or snapshot.get('signal_state')
				or payload.get('signal_state')
			)

			if signal_state is not None:
				is_waiting = signal_state != 'GREEN'
			else:
				is_waiting = active_green_lane != lane_id

			if is_waiting:
				total_wait += delta_seconds

	if total_ambulance_observations <= 0:
		return None
	return float(total_wait / total_ambulance_observations)

BASE_CROSSING_TIME = {
	"car": 1.8,
	"bike": 1.2,
	"ambulance": 1.5,
	"truck": 3.0,
	"bus": 2.5,
	"default": 1.8
}

def get_crossing_time(vehicle_index, vehicle_type):
	base_time = BASE_CROSSING_TIME.get(str(vehicle_type).lower() if vehicle_type else "default", BASE_CROSSING_TIME["default"])

	# Startup delay (first few vehicles slower)
	if vehicle_index == 0:
		return base_time + 1.0   # reaction + acceleration
	elif vehicle_index == 1:
		return base_time + 0.7
	elif vehicle_index == 2:
		return base_time + 0.4
	else:
		return base_time         # steady flow

# Run static replay and compute wait times
def run_static_replay(events, timer_duration):
	parsed = parse_event_log(events)
	timeline = reconstruct_vehicle_timeline(parsed)
	all_vehicles = [v for lane in (timeline or {}).values() for v in (lane or []) if isinstance(v, dict)]
	if not all_vehicles:
		return {'timeline': timeline, 'wait_time_records': [], 'timer_duration': timer_duration}
	sim_start = min(float(v.get('arrivedAt', 0.0) or 0.0) for v in all_vehicles)
	
	wait_time_records = []
	for lane_id, vehicles in timeline.items():
		if lane_id not in LANE_ORDER:
			continue
		lane_index = LANE_ORDER.index(lane_id)
		
		# Sort vehicles to process them chronologically
		valid_vehicles = [v for v in vehicles if isinstance(v, dict)]
		valid_vehicles.sort(key=lambda x: float(x.get('arrivedAt', 0.0) or 0.0))
		
		lane_crossing_time = 0.0
		for vehicle_index, v in enumerate(valid_vehicles):
			arrived_at_ms = float(v.get('arrivedAt', 0.0) or 0.0) - sim_start
			if arrived_at_ms < 0:
				arrived_at_ms = 0.0
			
			arrived_at = arrived_at_ms / 1000.0
			
			# Car waits until it arrives OR until the car in front of it finishes crossing
			earliest_possible = max(arrived_at, lane_crossing_time)
			
			# Get the true time the light is green for this car
			actual_cross_time = get_next_green_second(earliest_possible, lane_index)
			
			wait_time = actual_cross_time - arrived_at
			
			wait_time_records.append({
				'vehicleType': v.get('vehicleType'),
				'waitTime': wait_time,
				'laneId': lane_id,
				'arrivedAt': arrived_at,
			})
			
			# Block the lane realistically using startup delay and vehicle type
			lane_crossing_time = actual_cross_time + get_crossing_time(vehicle_index, v.get('vehicleType'))

	return {
		'timeline': timeline,
		'wait_time_records': wait_time_records,
		'timer_duration': timer_duration
	}


def _compute_static_total_crossed(wait_time_records, timer_duration):
	total = 0
	for record in wait_time_records or []:
		if not isinstance(record, dict):
			continue
		arrived_at = float(record.get('arrivedAt', 0.0) or 0.0)
		wait_time = float(record.get('waitTime', 0.0) or 0.0)
		crossed_at = arrived_at + wait_time
		if crossed_at < float(timer_duration):
			total += 1
	return int(total)


# Compute dynamic metrics from events
def compute_dynamic_metrics_from_rl_decisions(events, timer_duration):
	aggregated = _aggregate_snapshot_wait_queue(events)
	ambulance_wait = compute_ambulance_wait_time_from_decisions(events)
	if aggregated['num_decisions'] == 0:
		return {
			'avg_wait_time': 0.0,
			'total_vehicles_crossed': 0.0,
			'co2_estimate': 0.0,
			'avg_green_utilization': 0.0,
			'ambulance_avg_wait_time': ambulance_wait
		}

	vehicle_crossed_events = _vehicle_crossed_events(events)
	total_vehicles_crossed = len(vehicle_crossed_events)
	avg_green_utilization = 100.0 if aggregated['num_decisions'] > 0 and aggregated['avg_queue'] > 0 else 0.0

	return {
		'avg_wait_time': float(aggregated['avg_wait']),
		'total_vehicles_crossed': total_vehicles_crossed,
		'co2_estimate': float(aggregated['avg_wait'] * 2.3),
		'avg_green_utilization': avg_green_utilization,
		'ambulance_avg_wait_time': ambulance_wait
	}


def compute_dynamic_metrics(events, timer_duration=None):
	if timer_duration is None:
		timestamps = [float((event or {}).get('timestamp', 0) or 0) for event in (events or []) if isinstance(event, dict)]
		timer_duration = (max(timestamps) / 1000.0) if timestamps else 0.0

	parsed = parse_event_log(events)
	timeline = reconstruct_vehicle_timeline(parsed)
	snapshot_aggregated = _aggregate_snapshot_wait_queue(events)
	vehicle_crossed_events = _vehicle_crossed_events(events)
	total_vehicles_crossed = len(vehicle_crossed_events)
	print("MODE:", "RL")
	print("TOTAL CROSSED:", total_vehicles_crossed)
	# Build wait_time_records from vehicle_added and vehicle_crossed
	arrivals = {}
	for event in parsed:
		if not isinstance(event, dict):
			print('⚠️ Missing or invalid data:', event)
			continue
		if event.get('eventType') != 'vehicle_added':
			continue
		vehicle_id = event.get('vehicleId')
		if not vehicle_id:
			print('⚠️ Missing or invalid data:', event)
			continue
		arrivals[vehicle_id] = event

	crosses = [e for e in parsed if isinstance(e, dict) and e.get('eventType') == 'vehicle_crossed']
	wait_time_records = []
	for cross in crosses:
		if not isinstance(cross, dict):
			print('⚠️ Invalid cross event:', cross)
			continue

		vid = cross.get('vehicleId')
		if not vid:
			print('⚠️ Missing vehicleId in cross:', cross)
			continue

		lane_id = cross.get('laneId') or cross.get('lane_id')

		arrival = arrivals.get(vid)
		if not arrival or not isinstance(arrival, dict):
			print('⚠️ Missing arrival for vid:', vid)
			continue

		cross_ts = cross.get('timestamp')
		arrival_ts = arrival.get('timestamp')
		if cross_ts is None or arrival_ts is None:
			print('⚠️ Missing timestamps for vid:', vid)
			continue

		# Convert ms to seconds
		wait_time = (cross_ts - arrival_ts) / 1000
		wait_time_records.append({
			'vehicleType': cross.get('vehicleType'),
			'waitTime': wait_time,
			'laneId': lane_id
		})

	# Include stranded vehicles (those that spawned but never crossed) capped at the end of the simulation
	max_ts = max((float(e.get('timestamp', 0) or 0) for e in parsed if isinstance(e, dict) and e.get('timestamp')), default=None)
	if max_ts is None:
		import time
		max_ts = time.time() * 1000

	crossed_vids = set(c.get('vehicleId') for c in crosses if isinstance(c, dict) and c.get('vehicleId'))
	for vid, arrival in arrivals.items():
		if vid not in crossed_vids:
			arrival_ts = arrival.get('timestamp')
			if arrival_ts and max_ts > arrival_ts:
				wait_time = (max_ts - arrival_ts) / 1000
				wait_time_records.append({
					'vehicleType': arrival.get('vehicleType'),
					'waitTime': wait_time,
					'laneId': arrival.get('laneId', 'north')
				})

	ambulance_wait = compute_ambulance_wait_time(wait_time_records)
	if ambulance_wait is None:
		ambulance_wait = compute_ambulance_wait_time_from_decisions(events)
	metrics = {
		'avg_wait_time': compute_avg_wait_time([r['waitTime'] for r in wait_time_records]),
		'total_vehicles_crossed': total_vehicles_crossed,
		'co2_estimate': float(compute_avg_wait_time([r['waitTime'] for r in wait_time_records]) * 2.3),
		'avg_green_utilization': compute_green_utilization(timeline, CYCLE_DURATION, timer_duration),
		'ambulance_avg_wait_time': ambulance_wait
	}
	if metrics['total_vehicles_crossed'] == 0:
		return compute_dynamic_metrics_from_rl_decisions(events, timer_duration)
	return metrics

# Compute static metrics from events
def compute_static_metrics(events, timer_duration=None):
	if timer_duration is None:
		timestamps = [float((event or {}).get('timestamp', 0) or 0) for event in (events or []) if isinstance(event, dict)]
		timer_duration = (max(timestamps) / 1000.0) if timestamps else 0.0

	print("STATIC EVENTS COUNT:", len(events or []))
	print("STATIC EVENTS SAMPLE:", (events or [])[:10])

	replay = run_static_replay(events, timer_duration)
	wait_time_records = replay.get('wait_time_records', []) or []
	total_vehicles_crossed = _compute_static_total_crossed(wait_time_records, timer_duration)
	print("MODE:", "STATIC")
	print("TOTAL CROSSED:", total_vehicles_crossed)

	processed_records = []
	for r in wait_time_records:
		arrived_at = float(r.get('arrivedAt', 0.0) or 0.0)
		wait_duration = float(r.get('waitTime', 0.0) or 0.0)
		if arrived_at + wait_duration < float(timer_duration):
			processed_records.append(r)
		else:
			capped_wait = float(timer_duration) - arrived_at
			if capped_wait > 0:
				r['waitTime'] = capped_wait
				processed_records.append(r)

	if processed_records:
		avg_wait_time = compute_avg_wait_time([record.get('waitTime', 0.0) for record in processed_records])
	else:
		avg_wait_time = max(float(timer_duration) * 0.35, 5.0)

	return {
		'avg_wait_time': float(avg_wait_time),
		'total_vehicles_crossed': int(total_vehicles_crossed),
		'co2_estimate': float(avg_wait_time * 2.3),
		'avg_green_utilization': compute_green_utilization(replay.get('timeline', {}), CYCLE_DURATION, timer_duration),
		'ambulance_avg_wait_time': compute_ambulance_wait_time(processed_records) if processed_records else None
	}
