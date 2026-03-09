const BASE_URL = "http://localhost:8000"  // API base URL

// Create simulation session
export async function createSession(timerDuration) {
	const response = await fetch(`${BASE_URL}/simulation/start`, {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json'
		},
		body: JSON.stringify({ timer_duration: timerDuration })
	})
	// Parse and return JSON response
	return await response.json()
}

// POST lane snapshot to RL decision endpoint
export async function fetchRLDecision(snapshot) {
	const response = await fetch(`${BASE_URL}/rl/decision`, {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json'
		},
		body: JSON.stringify(snapshot)
	})
	// Parse and return JSON response
	return await response.json()
}

// POST event log to backend
export async function submitEventLog(sessionId, events) {
	// POST event log to backend
	const response = await fetch(`${BASE_URL}/simulation/submit-log`, {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json'
		},
		body: JSON.stringify({ session_id: sessionId, events: events })
	})
	// Parse and return JSON response
	return await response.json()
}

// GET simulation results for session
export async function fetchSimulationResults(sessionId) {
	// GET simulation results for session
	const response = await fetch(`${BASE_URL}/simulation/results/${sessionId}`, {
		method: 'GET',
		headers: {
			'Content-Type': 'application/json'
		}
	})
	// Parse and return JSON response
	return await response.json()
}
