import { moveVehicles, checkVehicleCrossing } from './vehicleUtils'

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
  const lane_state = {};
  const line_counts = {};
  const wait_time_by_direction = {};
  const queue_length_by_direction = {};
  const now = Date.now();

  for (const laneId of ['north', 'east', 'south', 'west']) {
    const vehicles = lanes[laneId] || [];
    const count = vehicles.length;
    const hasAmbulance = vehicles.some(v => v.vehicleType === 'ambulance');
    const toWaitSeconds = (vehicle) => {
      const baseTs = vehicle?.arrivalTime ?? vehicle?.spawnedAt ?? now;
      const elapsed = (now - Number(baseTs || now)) / 1000;
      return Number.isFinite(elapsed) && elapsed > 0 ? elapsed : 0;
    };
    const avgWaitTime = count > 0
      ? vehicles.reduce((sum, v) => sum + toWaitSeconds(v), 0) / count
      : 0;

    lane_state[laneId] = {
      count,
      hasAmbulance,
      avgWaitTime
    };
    line_counts[laneId] = count;
    wait_time_by_direction[laneId] = avgWaitTime;
    queue_length_by_direction[laneId] = count;
  }

  return {
    lane_state,
    line_counts,
    wait_time_by_direction,
    queue_length_by_direction
  };
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

function extractQueueCountsFromDecisionLog(log) {
  const snapshotQueues = log?.snapshot?.queue_length_by_direction
    || log?.debug?.snapshot?.queue_length_by_direction
    || log?.debug?.snapshot?.line_counts
    || null

  if (snapshotQueues && typeof snapshotQueues === 'object') {
    return {
      north: Number(snapshotQueues.north || 0),
      east: Number(snapshotQueues.east || 0),
      south: Number(snapshotQueues.south || 0),
      west: Number(snapshotQueues.west || 0)
    }
  }

  const laneMetrics = log?.debug?.lane_metrics || {}
  return {
    north: Number(laneMetrics?.north?.vehicle_count || 0),
    east: Number(laneMetrics?.east?.vehicle_count || 0),
    south: Number(laneMetrics?.south?.vehicle_count || 0),
    west: Number(laneMetrics?.west?.vehicle_count || 0)
  }
}

function normalizeSelectedLane(log) {
  const lane = (log?.selected_lane || log?.lane || '').toLowerCase()
  if (lane === 'north' || lane === 'east' || lane === 'south' || lane === 'west') {
    return lane
  }
  return 'north'
}

function createSyntheticVehicle(laneId, tick, index) {
  return {
    vehicleId: `static-${laneId}-${tick}-${index}-${Math.floor(Math.random() * 100000)}`,
    vehicleType: 'car',
    laneId,
    spawnedAt: Date.now(),
    position: 0
  }
}

function alignLaneCountsWithSnapshot(lanes, queueCounts, tick) {
  const next = {
    north: [...(lanes.north || [])],
    east: [...(lanes.east || [])],
    south: [...(lanes.south || [])],
    west: [...(lanes.west || [])]
  }

  for (const lane of ['north', 'east', 'south', 'west']) {
    const target = Math.max(0, Math.floor(Number(queueCounts[lane] || 0)))
    while (next[lane].length < target) {
      next[lane].push(createSyntheticVehicle(lane, tick, next[lane].length))
    }
    if (next[lane].length > target) {
      next[lane] = next[lane].slice(0, target)
    }
  }

  return next
}

export function computeCrossedFromDecisionLogsWithSharedPhysics(decisionLogs) {
  const ordered = [...(decisionLogs || [])].sort((a, b) => Number(a?.tick || 0) - Number(b?.tick || 0))
  if (!ordered.length) {
    return { totalCrossed: 0, ticksProcessed: 0 }
  }

  let lanes = { north: [], east: [], south: [], west: [] }
  let totalCrossed = 0

  for (const log of ordered) {
    const tick = Number(log?.tick || 0)
    const selectedLane = normalizeSelectedLane(log)
    const queueCounts = extractQueueCountsFromDecisionLog(log)

    lanes = alignLaneCountsWithSnapshot(lanes, queueCounts, tick)

    const beforeCount = lanes[selectedLane].length

    const moved = moveVehicles(lanes, {
      north: selectedLane === 'north' ? 'green' : 'red',
      east: selectedLane === 'east' ? 'green' : 'red',
      south: selectedLane === 'south' ? 'green' : 'red',
      west: selectedLane === 'west' ? 'green' : 'red'
    })

    const afterCross = { north: [], east: [], south: [], west: [] }
    let crossedCount = 0

    for (const lane of ['north', 'east', 'south', 'west']) {
      for (const vehicle of moved[lane]) {
        if (lane !== selectedLane) {
          afterCross[lane].push(vehicle)
          continue
        }
        const cross = checkVehicleCrossing(vehicle)
        if (cross.crossed) {
          crossedCount += 1
        } else {
          afterCross[lane].push(vehicle)
        }
      }
    }

    const afterCount = afterCross[selectedLane].length
    console.log('STATIC → Lane:', selectedLane, 'Before:', beforeCount, 'After:', afterCount)
    console.log('CROSSED:', crossedCount)

    totalCrossed += crossedCount
    lanes = afterCross
  }

  return {
    totalCrossed,
    ticksProcessed: ordered.length
  }
}