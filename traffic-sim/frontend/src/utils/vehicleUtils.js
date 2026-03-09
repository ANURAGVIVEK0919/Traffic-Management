// Move vehicles based on light states
export function moveVehicles(lanes, lightStates) {
  const updatedLanes = {}
  for (const lane of ['north', 'south', 'east', 'west']) {
    updatedLanes[lane] = lanes[lane].map(vehicle => {
      if (lightStates[lane] === 'green') {
        // Move vehicle forward by 0.5 units
        return { ...vehicle, position: (vehicle.position || 0) + 0.5 }
      }
      // Vehicle does not move
      return { ...vehicle }
    })
  }
  return updatedLanes
}

// Check if vehicle has crossed
export function checkVehicleCrossing(vehicle) {
  if ((vehicle.position || 0) >= 5) {
    return { crossed: true, waitTime: vehicle.spawnedAt }
  }
  return { crossed: false, waitTime: 0 }
}
