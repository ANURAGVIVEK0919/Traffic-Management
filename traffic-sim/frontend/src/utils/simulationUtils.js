// Validate timer input
export function validateTimerInput(value) {
  const num = Number(value)
  if (num >= 1 && num <= 10) {
    return { valid: true, error: null }
  }
  return { valid: false, error: 'Timer must be between 1 and 10 minutes' }
}

// Generate vehicle ID
export function generateVehicleId(vehicleType, laneId) {
  const rand = Math.floor(1000 + Math.random() * 9000)
  return `${vehicleType}-${laneId}-${rand}`
}

// Build lane snapshot
export function buildLaneSnapshot(lanes) {
  const lane_states = ['north', 'east', 'south', 'west'].map(laneId => {
    const vehicles = lanes[laneId] || [];
    const vehicle_count = vehicles.length;
    const has_ambulance = vehicles.some(v => v.vehicleType === 'ambulance');
    // avg_wait_time in seconds
    const now = Date.now();
    const avg_wait_time = vehicle_count > 0
      ? vehicles.reduce((sum, v) => sum + ((now - v.spawnedAt) / 1000), 0) / vehicle_count
      : 0;
    return {
      lane_id: laneId,
      vehicle_count,
      has_ambulance,
      avg_wait_time
    };
  });
  return { lane_states };
}

// Check simulation end
export function checkSimulationEnd(timeRemaining) {
  if (timeRemaining <= 0) {
    return { ended: true };
  }
  return { ended: false };
}

// Check for ambulance in any lane
export function hasAmbulanceInAnyLane(lanes) {
  for (const lane of ['north', 'south', 'east', 'west']) {
    const vehicles = lanes[lane] || []
    if (vehicles.some(v => v.vehicleType === 'ambulance')) {
      return { present: true }
    }
  }
  return { present: false }
}
