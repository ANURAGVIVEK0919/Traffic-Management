const BASE_URL = "http://localhost:8000"  // API base URL

function extractSignalPhasesFromDecisionLogs(decisionLogs) {
	if (!Array.isArray(decisionLogs) || decisionLogs.length === 0) {
		return []
	}

	for (let i = decisionLogs.length - 1; i >= 0; i -= 1) {
		const snapshot = decisionLogs[i]?.snapshot
		const phases = snapshot?.signal_phases
		if (Array.isArray(phases) && phases.length > 0) {
			return phases
		}
	}

	return []
}

async function enrichWithSignalPhases(result, sessionId) {
	if (!result || Array.isArray(result?.signal_phases)) {
		return result
	}

	try {
		const logsPayload = await fetchDecisionLogs(sessionId)
		const phases = extractSignalPhasesFromDecisionLogs(logsPayload?.decisionLogs)
		return {
			...result,
			signal_phases: phases
		}
	} catch {
		return {
			...result,
			signal_phases: []
		}
	}
}

function resolveSessionId(value) {
	if (typeof value === 'string' && value.trim()) {
		return value
	}
	if (value && typeof value === 'object') {
		return value.sessionId || value.session_id || null
	}
	return null
}

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

export async function fetchLiveCounts() {
	const response = await fetch(`${BASE_URL}/simulation/results/latest`, {
		method: 'GET',
		cache: 'no-store',
		headers: {
			'Content-Type': 'application/json'
		}
	})
	const data = await response.json()
	console.log('API:', data?.lane_counts)
	return Array.isArray(data?.lane_counts) ? data.lane_counts : [0, 0, 0, 0]
}

// POST lane snapshot to RL decision endpoint
export async function fetchRLDecision(snapshot) {
	const laneState = snapshot?.lane_state || {}
	const rlPayload = {
		lane_counts: [
			Number(laneState?.north?.count || 0),
			Number(laneState?.south?.count || 0),
			Number(laneState?.east?.count || 0),
			Number(laneState?.west?.count || 0)
		],
		timestamp: Number(snapshot?.timestamp || Date.now() / 1000),
		active_green_lane: snapshot?.active_green_lane || null,
		source: 'frontend_fetchRLDecision',
		rl_call_timestamp: Date.now() / 1000
	}

	try {
		const response = await fetch(`${BASE_URL}/rl/decision`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json'
			},
			body: JSON.stringify(rlPayload)
		})

		if (!response.ok) {
			throw new Error(`RL decision request failed with status ${response.status}`)
		}

		const data = await response.json()
		console.log('RL decision:', data)
		if (data && typeof data === 'object') {
			return data
		}
	} catch (error) {
		console.warn('fetchRLDecision fallback:', error)
		return {
			lane: 'north',
			duration: 5,
			debug: {
				source: 'frontend_fallback'
			}
		}
	}

	return {
		lane: 'north',
		duration: 5,
		debug: {
			source: 'frontend_fallback_invalid_response'
		}
	}
}

// POST event log to backend
export async function submitEventLog(sessionId, events) {
	const resolvedSessionId = resolveSessionId(sessionId)
	// POST event log to backend
	const response = await fetch(`${BASE_URL}/simulation/submit-log`, {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json'
		},
		body: JSON.stringify({ session_id: resolvedSessionId, events: events })
	})
	// Parse and return JSON response
	return await response.json()
}

export async function logSignalPhase(sessionId, lane, duration) {
	const resolvedSessionId = resolveSessionId(sessionId)
	if (!resolvedSessionId) {
		throw new Error('Missing sessionId for signal phase log request')
	}

	const response = await fetch(`${BASE_URL}/simulation/log`, {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json'
		},
		body: JSON.stringify({
			session_id: resolvedSessionId,
			lane,
			duration
		})
	})

	return await response.json()
}

// GET simulation results for session
export async function fetchSimulationResults(sessionIdOrPair, staticSessionId = null) {
	const isPairObject = sessionIdOrPair && typeof sessionIdOrPair === 'object' && !Array.isArray(sessionIdOrPair)
	const rlId = isPairObject ? resolveSessionId(sessionIdOrPair.rlId || sessionIdOrPair.rl_id) : resolveSessionId(sessionIdOrPair)
	const staticId = isPairObject ? resolveSessionId(sessionIdOrPair.staticId || sessionIdOrPair.static_id) : resolveSessionId(staticSessionId)

	if (rlId && staticId) {
		const params = new URLSearchParams({ rl_id: rlId, static_id: staticId })
		const response = await fetch(`${BASE_URL}/simulation/results?${params.toString()}`, {
			method: 'GET',
			cache: 'no-store',
			headers: {
				'Content-Type': 'application/json'
			}
		})
			const result = await response.json()
			return await enrichWithSignalPhases(result, rlId)
	}

	if (!rlId) {
		throw new Error('Missing sessionId for simulation results request')
	}

	const response = await fetch(`${BASE_URL}/simulation/results/${rlId}`, {
		method: 'GET',
		cache: 'no-store',
		headers: {
			'Content-Type': 'application/json'
		}
	})
		const result = await response.json()
		return await enrichWithSignalPhases(result, rlId)
}

// GET per-tick RL decision logs for session
export async function fetchDecisionLogs(sessionId) {
	const resolvedSessionId = resolveSessionId(sessionId)
	if (!resolvedSessionId) {
		throw new Error('Missing sessionId for decision log request')
	}
	const response = await fetch(`${BASE_URL}/simulation/decision-log/${resolvedSessionId}`, {
		method: 'GET',
		headers: {
			'Content-Type': 'application/json'
		}
	})
	return await response.json()
}

// GET summarized session report for a session
export async function fetchSessionReport(sessionId) {
	const resolvedSessionId = resolveSessionId(sessionId)
	if (!resolvedSessionId) {
		throw new Error('Missing sessionId for session report request')
	}
	const response = await fetch(`${BASE_URL}/simulation/report/${resolvedSessionId}`, {
		method: 'GET',
		headers: {
			'Content-Type': 'application/json'
		}
	})
	return await response.json()
}

export async function uploadVideo(file) {
	const formData = new FormData()
	formData.append('video', file)
	const response = await fetch(`${BASE_URL}/upload/video`, {
		method: 'POST',
		body: formData
	})
	return await response.json()
}

export async function startVideoJob(sessionId, videoPath) {
	const resolvedSessionId = resolveSessionId(sessionId)
	const response = await fetch(`${BASE_URL}/jobs/start`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ session_id: resolvedSessionId, video_path: videoPath })
	})
	const result = await response.json()

	const sid =
		result.session_id ||
		result?.sessionId ||
		result?.data?.session_id ||
		result?.data?.sessionId

	if (!sid) {
		throw new Error("Session ID missing in job response")
	}

	result.session_id = sid
	return result
}

export async function getJobStatus(sessionId) {
	const resolvedSessionId = resolveSessionId(sessionId)
	const response = await fetch(`${BASE_URL}/jobs/${resolvedSessionId}/status`, {
		method: 'GET',
		headers: { 'Content-Type': 'application/json' }
	})
	return await response.json()
}
