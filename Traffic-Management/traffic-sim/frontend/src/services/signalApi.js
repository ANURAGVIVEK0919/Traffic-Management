const BASE_URL = 'http://localhost:8000';

/**
 * Call the neural net to get recommended green-phase duration.
 * Falls back to math formula result if the API is unreachable.
 *
 * @param {object} trafficState - { lane_counts, wait_times, ambulance, current_lane, elapsed_time }
 * @param {number} mathFallback - result from the old math formula (used if API fails)
 * @returns {Promise<number>} - recommended duration in seconds
 */
export async function getModelDuration(trafficState, mathFallback = 8) {
  try {
    const res = await fetch(`${BASE_URL}/signal/decision`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(trafficState),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    return Number(data.recommended_duration) || mathFallback;
  } catch (err) {
    console.warn('[SignalAPI] getModelDuration failed, using math fallback:', err.message);
    return mathFallback;
  }
}

/**
 * Ask Gemini to explain the current signal decision.
 * Non-blocking — called after lane switch.
 *
 * @param {object} trafficState - { lane_counts, wait_times, ambulance, current_lane }
 * @param {number} decisionMade - the duration that was actually applied
 * @returns {Promise<string>} - plain English explanation
 */
export async function explainDecision(trafficState, decisionMade) {
  try {
    const res = await fetch(`${BASE_URL}/signal/explain`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...trafficState, decision_made: decisionMade }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    return data.explanation || '';
  } catch (err) {
    console.warn('[SignalAPI] explainDecision failed:', err.message);
    return '';
  }
}

/**
 * Send a natural language configuration command to Gemini.
 *
 * @param {string} command - e.g. "reduce max green to 20 seconds"
 * @returns {Promise<{params: object, acknowledged: string}>}
 */
export async function applyConfig(command) {
  try {
    const res = await fetch(`${BASE_URL}/signal/configure`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    console.warn('[SignalAPI] applyConfig failed:', err.message);
    return {
      params: {},
      acknowledged: 'Could not reach configuration service. Please try again.',
    };
  }
}
