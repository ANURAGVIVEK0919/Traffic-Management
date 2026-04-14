const GREEN_LANE_STEP = 1.2;
const CROSSING_POSITION_THRESHOLD = 3;

// Move vehicles based on light states
export function moveVehicles(lanes, lightStates) {
  const updatedLanes = {}
  for (const lane of ['north', 'south', 'east', 'west']) {
    updatedLanes[lane] = lanes[lane].map(vehicle => {
      if (lightStates[lane] === 'green') {
        // Simulation-only discharge speed for visible queue decay under green.
        return { ...vehicle, position: (vehicle.position || 0) + GREEN_LANE_STEP }
      }
      // Vehicle does not move
      return { ...vehicle }
    })
  }
  return updatedLanes
}

// Check if vehicle has crossed
export function checkVehicleCrossing(vehicle) {
  if ((vehicle.position || 0) >= CROSSING_POSITION_THRESHOLD) {
    return { crossed: true, waitTime: vehicle.spawnedAt }
  }
  return { crossed: false, waitTime: 0 }
}
