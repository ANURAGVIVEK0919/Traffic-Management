
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
def compute_green_utilization(timeline, actual_signal_log, timer_duration):
    """
    More realistic utilization: 
    Actual Time Used by Vehicles / Total Green Time Offered.
    """
    if not actual_signal_log:
        return 0.0
    
    total_green_time = sum(float(p.get('duration', 0)) for p in actual_signal_log)
    if total_green_time <= 0:
        return 0.0
        
    all_vehicles = [v for lane in timeline.values() for v in lane]
    if not all_vehicles:
        return 0.0
        
    sim_start = min(float(v.get('arrivedAt', 0)) for v in all_vehicles)
    
    # Saturation flow: approx 1 vehicle per 2 seconds of green
    # We calculate how much green time was 'useful'
    useful_green_time = 0.0
    
    for phase in actual_signal_log:
        lane = phase.get('lane')
        duration = float(phase.get('duration', 0))
        # Approximate start time of phase if not provided
        # (Assuming phases occur sequentially throughout the timer_duration)
        
        vehicles_in_lane = timeline.get(lane, [])
        # Count vehicles that arrived before this phase ended
        # and haven't been cleared by previous phases.
        # This is a heuristic since we don't have exact phase timestamps.
        total_vehicles = len([v for v in vehicles_in_lane if (float(v.get('arrivedAt', 0)) - sim_start) < (float(timer_duration) * 1000)])
        
        # A lane is only "saturated" if it has many vehicles.
        if total_vehicles > 0:
            num_phases = len([p for p in actual_signal_log if p.get('lane') == lane])
            avg_vehicles_per_phase = total_vehicles / max(1, num_phases)
            
            # More nuanced saturation:
            # 1 vehicle = ~2.5s usage
            # Each subsequent vehicle = ~1.8s
            usage_per_phase = 2.5 + (max(0, avg_vehicles_per_phase - 1) * 1.8)
            consumed = min(duration, usage_per_phase)
            useful_green_time += consumed
        
    return min(96.5, (useful_green_time / total_green_time) * 100.0) if total_green_time > 0 else 0.0

# Compute average ambulance wait time
def compute_ambulance_wait_time(wait_time_records):
    if not wait_time_records:
        return None
    times = [
        float(rec.get('waitTime', 0)) 
        for rec in wait_time_records 
        if str(rec.get('vehicleType', '')).lower() == 'ambulance'
    ]
    if not times:
        return None
    return float(sum(times) / len(times))
