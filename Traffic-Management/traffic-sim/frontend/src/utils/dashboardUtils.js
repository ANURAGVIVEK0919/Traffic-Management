// Determine which simulation (dynamic RL or static replay) performed better for a given metric
// Pure function, no side effects

export function determineWinner(metricKey, dynamicValue, staticValue) {
  // If either value is null, no winner
  if (dynamicValue === null || staticValue === null) {
    return { winner: 'n/a', explanation: 'No data available' };
  }

  // Metrics where lower is better
  const lowerIsBetter = ['avg_wait_time', 'co2_estimate', 'ambulance_avg_wait_time'];
  // Metrics where higher is better
  const higherIsBetter = ['total_vehicles_crossed', 'avg_green_utilization'];

  if (lowerIsBetter.includes(metricKey)) {
    if (dynamicValue < staticValue) {
      return { winner: 'dynamic', explanation: 'Dynamic RL achieved a better (lower) value.' };
    } else if (staticValue < dynamicValue) {
      return { winner: 'static', explanation: 'Static replay achieved a better (lower) value.' };
    } else {
      return { winner: 'tie', explanation: 'Both methods achieved the same value.' };
    }
  }

  if (higherIsBetter.includes(metricKey)) {
    if (dynamicValue > staticValue) {
      return { winner: 'dynamic', explanation: 'Dynamic RL achieved a better (higher) value.' };
    } else if (staticValue > dynamicValue) {
      return { winner: 'static', explanation: 'Static replay achieved a better (higher) value.' };
    } else {
      return { winner: 'tie', explanation: 'Both methods achieved the same value.' };
    }
  }

  // Unknown metric
  return { winner: 'n/a', explanation: 'Unknown metric key.' };
}
