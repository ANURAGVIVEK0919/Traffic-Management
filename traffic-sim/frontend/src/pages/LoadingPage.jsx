import { useEffect } from 'react'
import { useSimulationStore } from '../state/simulationStore'
import { submitEventLog } from '../services/api'
import { useNavigate } from 'react-router-dom'

// LoadingPage component
export default function LoadingPage() {
  const sessionId = useSimulationStore((state) => state.sessionId)
  const eventLog = useSimulationStore((state) => state.eventLog)
  const navigate = useNavigate()

  // Submit event log and handle navigation
  useEffect(() => {
    async function handleSubmit() {
      try {
        const response = await submitEventLog(sessionId, eventLog)
        if (response.success) {
          navigate(`/dashboard/${sessionId}`)
        } else {
          alert('Failed to process results. Please try again.')
        }
      } catch {
        alert('Failed to process results. Please try again.')
      }
    }
    handleSubmit()
  }, [])

  return (
    <>
      <div>Processing simulation results...</div>
      <p>Please wait while we run the static system replay.</p>
    </>
  )
}