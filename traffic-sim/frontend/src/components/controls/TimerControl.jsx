
import { useState } from 'react'  // React state
import { useSimulationStore } from '../../state/simulationStore'
import { createSession } from '../../services/api'

// TimerControl component
export default function TimerControl() {
	const [inputValue, setInputValue] = useState('')  // Local input state
	const setTimer = useSimulationStore((state) => state.setTimer)
	const setSessionId = useSimulationStore((state) => state.setSessionId)

	// Validate timer input
	function validateTimerInput(value) {
		const num = Number(value)
		if (num >= 1 && num <= 10) {
			return { valid: true, error: null }
		}
		return { valid: false, error: 'Timer must be between 1 and 10 minutes' }
	}

	// Handle confirm button click
	async function handleConfirm() {
		const { valid, error } = validateTimerInput(inputValue)
		if (!valid) {
			alert(error)
			return
		}
		const seconds = Number(inputValue) * 60
		setTimer(seconds)
		const result = await createSession(seconds)
		setSessionId(result.session_id)
	}

	return (
		<>
			{/* Timer label */}
			<label>Set Timer (1-10 minutes)</label>
			{/* Timer input */}
			<input
				type="number"
				value={inputValue}
				onChange={e => setInputValue(e.target.value)}
			/>
			{/* Confirm button */}
			<button onClick={handleConfirm}>Confirm</button>
		</>
	)
}
