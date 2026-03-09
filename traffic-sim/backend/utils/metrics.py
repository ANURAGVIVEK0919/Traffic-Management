
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
		'car': 2.3,
		'bike': 0.5,
		'ambulance': 3.0,
		'truck': 5.0,
		'bus': 4.5
	}
	total = 0.0
	for rec in wait_time_records:
		rate = rates.get(rec['vehicleType'], 2.0)
		total += rate * rec['waitTime']
	return float(total)

# Compute green utilization percentage
def compute_green_utilization(timeline, cycle_duration, timer_duration):
	all_vehicles = [v for lane in timeline.values() for v in lane]
	if not all_vehicles:
		return 0.0
	sim_start = min(v['arrivedAt'] for v in all_vehicles)
	phases = int(timer_duration / 15)
	utilized = 0
	for phase in range(phases):
		lane = ['north', 'east', 'south', 'west'][phase % 4]
		waiting = any((v['arrivedAt'] - sim_start) <= phase * 15 for v in timeline.get(lane, []))
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
