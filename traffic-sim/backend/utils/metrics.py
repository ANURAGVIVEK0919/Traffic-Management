
# Compute average wait time
def compute_avg_wait_time(wait_times):
	if not wait_times:
		return 0.0
	return float(sum(wait_times) / len(wait_times))

# Compute total vehicles crossed
def compute_total_crossed(timeline, cycle_duration, timer_duration):
	count = sum(len(vehicles) for vehicles in timeline.values())
	return count

# Compute CO2 estimate
def compute_co2_estimate(wait_time_records):
	rates = {
		'car': 0.28,
		'bike': 0.15,
		'ambulance': 0.6,
		'truck': 2.0,
		'bus': 0.8
	}
	total = 0.0
	for rec in wait_time_records:
		rate = rates.get(rec.get('vehicleType') if isinstance(rec, dict) else None, 0.3)
		wait_time = rec.get('waitTime') if isinstance(rec, dict) else None
		total += rate * (0 if wait_time is None else wait_time)
	return float(total)

# Compute green utilization percentage
def compute_green_utilization(timeline, cycle_duration, timer_duration):
	all_vehicles = [v for lane in timeline.values() for v in lane]
	if not all_vehicles:
		return 0.0
	sim_start = min(v['arrivedAt'] for v in all_vehicles)
	phase_duration = cycle_duration / 4
	phases = int(timer_duration / phase_duration)
	utilized = 0
	for phase in range(phases):
		lane = ['north', 'west', 'south', 'east'][phase % 4]
		waiting = any((v['arrivedAt'] - sim_start) <= phase * phase_duration for v in timeline.get(lane, []))
		if waiting:
			utilized += 1
	if phases == 0:
		return 0.0
	return float(utilized) / phases * 100.0

# Compute average ambulance wait time
def compute_ambulance_wait_time(wait_time_records):
	times = [rec['waitTime'] for rec in wait_time_records if rec['vehicleType'] == 'ambulance']
	if not times:
		return None
	return float(sum(times) / len(times))
