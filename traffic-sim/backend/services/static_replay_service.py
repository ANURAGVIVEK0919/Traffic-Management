
from backend.utils.event_parser import parse_event_log, reconstruct_vehicle_timeline
from backend.utils.metrics import (
	compute_avg_wait_time,
	compute_total_crossed,
	compute_co2_estimate,
	compute_green_utilization,
	compute_ambulance_wait_time
)

STATIC_GREEN_DURATION = 15  # seconds per lane
CYCLE_DURATION = 60  # full cycle
LANE_ORDER = ['north', 'east', 'south', 'west']

# Compute wait time for a vehicle in static replay
def compute_vehicle_wait_time(vehicle, lane, timer_duration, sim_start=0):
	if not lane or lane not in LANE_ORDER:
		return 0.0
	arrived = vehicle.get('arrivedAt', 0) - sim_start  # normalize to 0-based
	lane_index = LANE_ORDER.index(lane)
	# Find first green start time >= arrivedAt
	cycles = int(timer_duration / CYCLE_DURATION) + 1
	green_start = None
	for cycle in range(cycles):
		start = cycle * CYCLE_DURATION + lane_index * STATIC_GREEN_DURATION
		if start >= arrived:
			green_start = start
			break
	if green_start is None:
		green_start = timer_duration
	return max(0.0, green_start - arrived)

# Run static replay and compute wait times
def run_static_replay(events, timer_duration):
	parsed = parse_event_log(events)
	timeline = reconstruct_vehicle_timeline(parsed)
	print('Static timeline:', timeline)
	all_vehicles = [v for lane in timeline.values() for v in lane]
	if not all_vehicles:
		return {'timeline': timeline, 'wait_time_records': [], 'timer_duration': timer_duration}
	sim_start = min(v['arrivedAt'] for v in all_vehicles)
	wait_time_records = []
	for lane_id, vehicles in timeline.items():
		for v in vehicles:
			wait_time = compute_vehicle_wait_time(v, lane_id, timer_duration, sim_start)
			wait_time_records.append({
				'vehicleType': v['vehicleType'],
				'waitTime': wait_time
			})
	print('Static wait_time_records:', wait_time_records)
	return {
		'timeline': timeline,
		'wait_time_records': wait_time_records,
		'timer_duration': timer_duration
	}

# Compute dynamic metrics from events
def compute_dynamic_metrics(events, timer_duration):
	parsed = parse_event_log(events)
	timeline = reconstruct_vehicle_timeline(parsed)
	# Build wait_time_records from vehicle_added and vehicle_crossed
	arrivals = {e['vehicleId']: e for e in parsed if e['eventType'] == 'vehicle_added'}
	crosses = [e for e in parsed if e['eventType'] == 'vehicle_crossed']
	wait_time_records = []
	for cross in crosses:
		vid = cross['vehicleId']
		lane_id = cross.get('laneId') or cross.get('lane_id')
		if vid in arrivals:
			# Convert ms to seconds
			wait_time = (cross['timestamp'] - arrivals[vid]['timestamp']) / 1000
			wait_time_records.append({
				'vehicleType': cross['vehicleType'],
				'waitTime': wait_time,
				'laneId': lane_id
			})
	metrics = {
		'avg_wait_time': compute_avg_wait_time([r['waitTime'] for r in wait_time_records]),
		'total_vehicles_crossed': len(wait_time_records),
		'co2_estimate': compute_co2_estimate(wait_time_records),
		'avg_green_utilization': compute_green_utilization(timeline, CYCLE_DURATION, timer_duration),
		'ambulance_avg_wait_time': compute_ambulance_wait_time(wait_time_records)
	}
	return metrics

# Compute static metrics from events
def compute_static_metrics(events, timer_duration):
	replay = run_static_replay(events, timer_duration)
	timeline = replay['timeline']
	wait_time_records = replay['wait_time_records']
	metrics = {
		'avg_wait_time': compute_avg_wait_time([r['waitTime'] for r in wait_time_records]),
		'total_vehicles_crossed': compute_total_crossed(timeline, CYCLE_DURATION, timer_duration),
		'co2_estimate': compute_co2_estimate(wait_time_records),
		'avg_green_utilization': compute_green_utilization(timeline, CYCLE_DURATION, timer_duration),
		'ambulance_avg_wait_time': compute_ambulance_wait_time(wait_time_records)
	}
	return metrics
