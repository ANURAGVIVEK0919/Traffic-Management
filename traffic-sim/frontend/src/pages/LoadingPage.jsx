import { useEffect, useState } from 'react';
import { useSimulationStore } from '../state/simulationStore';
import { submitEventLog, fetchSimulationResults } from '../services/api';
import { useNavigate } from 'react-router-dom';
import AppSidebar from '../components/layout/AppSidebar';
import Card from '../components/ui/Card';
import './dashboard.css';

export default function LoadingPage() {
  const sessionId = useSimulationStore((state) => state.sessionId);
  const setSessionId = useSimulationStore((state) => state.setSessionId);
  const eventLog = useSimulationStore((state) => state.eventLog);
  const signalPhases = useSimulationStore((state) => state.signalPhases);
  const totalVehiclesCrossed = useSimulationStore((state) => state.totalVehiclesCrossed);
  const [statusMessage, setStatusMessage] = useState('Processing simulation results...');
  const [errorMessage, setErrorMessage] = useState(null);
  const navigate = useNavigate();

  function persistFrontendSummary(finalSessionId) {
    if (typeof window === 'undefined' || !finalSessionId) {
      return;
    }

    const summary = {
      totalVehiclesCrossed,
      signalPhases: Array.isArray(signalPhases) ? signalPhases : []
    };

    window.sessionStorage.setItem(`traffic-sim-summary:${finalSessionId}`, JSON.stringify(summary));
  }

  async function waitForResults(sessionIdToCheck, maxRetries = 10, retryDelayMs = 1000) {
    for (let attempt = 1; attempt <= maxRetries; attempt += 1) {
      try {
        const results = await fetchSimulationResults(sessionIdToCheck);
        if (results && !results.error) {
          return true;
        }
      } catch {
        // Keep retrying until max retries are exhausted.
      }

      if (attempt < maxRetries) {
        await new Promise((resolve) => setTimeout(resolve, retryDelayMs));
      }
    }

    return false;
  }

  useEffect(() => {
    async function handleSubmit() {
      setErrorMessage(null);
      try {
        console.log('FRONTEND session_id:', sessionId);
        const response = await submitEventLog(sessionId, eventLog);
        const jobId = response?.job_id || response?.jobId || null;
        const finalSessionId =
          response?.session_id ||
          response?.sessionId ||
          sessionId ||
          null;

        console.log('Job ID:', jobId);
        console.log('Session ID:', finalSessionId);

        if (response.success) {
          if (!finalSessionId) {
            setErrorMessage('Session ID missing in job response. Cannot open dashboard.');
            return;
          }

          setStatusMessage('Finalizing results...');
          persistFrontendSummary(finalSessionId);
          console.log('FRONTEND finalSessionId before navigation:', finalSessionId);
          const ready = await waitForResults(finalSessionId, 10, 1000);
          if (!ready) {
            setErrorMessage('Results not ready, please retry');
            return;
          }

          setSessionId(finalSessionId);
          navigate(`/dashboard/${finalSessionId}`);
        } else {
          setErrorMessage('Failed to process results. Please try again.');
        }
      } catch {
        setErrorMessage('Failed to process results. Please try again.');
      }
    }
    handleSubmit();
  }, [eventLog, navigate, sessionId, setSessionId]);

  return (
    <div className="dashboard">
      <AppSidebar />

      <main className="content loading-content">
        <Card className="card-section loading-card">
          <div className="loading-spinner" aria-hidden="true" />
          <h2>Processing Simulation...</h2>
          <p className="muted-text">{statusMessage}</p>
          <p className="muted-text">Please wait while we run the static system replay.</p>
          {errorMessage && <p className="alert alert-high">{errorMessage}</p>}
        </Card>
      </main>
    </div>
  );
}
