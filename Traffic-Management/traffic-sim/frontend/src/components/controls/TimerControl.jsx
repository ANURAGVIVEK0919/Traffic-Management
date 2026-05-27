
import { useState } from 'react'  // React state
import { useSimulationStore } from '../../state/simulationStore'
import { createSession } from '../../services/api'
import Button from '../ui/Button'

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
		console.log('FRONTEND session_id:', result.session_id)
		setSessionId(result.session_id)
	}

	return (
		<div className="form-row" style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginTop: '1rem' }}>
			{/* Timer label */}
			<label className="input-label" style={{ marginBottom: 0 }}>Set Timer (1-10 minutes)</label>
			{/* Timer input */}
			<input
				type="number"
				className="input-control"
				style={{ width: '100px' }}
				value={inputValue}
				onChange={e => setInputValue(e.target.value)}
			/>
			{/* Confirm button */}
			<Button onClick={handleConfirm}>Confirm</Button>
		</div>
	)
}
