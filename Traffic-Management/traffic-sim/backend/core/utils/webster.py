def compute_webster_optimal_cycle(lane_counts, saturation_flow=0.5):
    """
    Computes optimal cycle length using Webster's Formula.
    C = (1.5L + 5) / (1 - sum(Y))
    
    L: Total lost time per cycle (approx 4s per phase for 4 phases = 16s)
    Y: Ratio of flow to saturation flow for critical lanes.
    """
    lost_time_per_phase = 4.0
    num_phases = 4
    L = lost_time_per_phase * num_phases
    
    # Estimate flows (vehicles per second)
    # We assume a 60s window for the current counts to represent flow
    flows = {lane: count / 60.0 for lane, count in lane_counts.items()}
    
    # Y is the sum of ratios for critical phases (North-South, East-West)
    # Here we treat all 4 directions as separate phases for simplicity
    Y_sum = sum(min(0.2, flow / saturation_flow) for flow in flows.values())
    
    # Avoid division by zero
    if Y_sum >= 0.95:
        Y_sum = 0.95
        
    optimal_cycle = (1.5 * L + 5) / (1 - Y_sum)
    
    # Cap between 40s and 120s
    return max(40.0, min(120.0, optimal_cycle))

def get_webster_durations(lane_counts, saturation_flow=0.5):
    """
    Allocates green time based on flow ratios.
    """
    cycle = compute_webster_optimal_cycle(lane_counts, saturation_flow)
    lost_time = 4.0 * 4
    available_green = cycle - lost_time
    
    total_flow = sum(lane_counts.values())
    if total_flow == 0:
        return {lane: available_green / 4 for lane in lane_counts}
        
    durations = {}
    for lane, count in lane_counts.items():
        # Proportionate allocation
        durations[lane] = (count / total_flow) * available_green
        # Enforce minimums
        durations[lane] = max(8.0, durations[lane])
        
    return durations
