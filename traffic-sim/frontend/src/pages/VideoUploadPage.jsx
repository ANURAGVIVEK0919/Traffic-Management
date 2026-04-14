import { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { uploadVideo, startVideoJob, getJobStatus } from '../services/api';
import { useSimulationStore } from '../state/simulationStore';
import AppSidebar from '../components/layout/AppSidebar';
import Button from '../components/ui/Button';
import Section from '../components/ui/Section';
import './dashboard.css';

export default function VideoUploadPage() {
  const setTimer = useSimulationStore((state) => state.setTimer);
  const resetStore = useSimulationStore((state) => state.resetStore);
  const setSessionIdStore = useSimulationStore((state) => state.setSessionId);
  const setMode = useSimulationStore((state) => state.setMode);
  const updateVehiclePositions = useSimulationStore((state) => state.updateVehiclePositions);
  const setTotalVehiclesCrossed = useSimulationStore((state) => state.setTotalVehiclesCrossed);
  const setSignalPhases = useSimulationStore((state) => state.setSignalPhases);
  const logEvent = useSimulationStore((state) => state.logEvent);
  const startSimulation = useSimulationStore((state) => state.startSimulation);
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const [videoPath, setVideoPath] = useState(null);
  const [jobStarted, setJobStarted] = useState(false);
  const [jobStatus, setJobStatus] = useState(null);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState(null);
  const intervalRef = useRef(null);
  const navigate = useNavigate();

  function emptyLanes() {
    return { north: [], east: [], south: [], west: [] };
  }

  function normalizeSimulationLanes(simulationState) {
    const lanes = simulationState?.lanes || {};
    const normalized = emptyLanes();
    const now = Date.now();

    for (const lane of ['north', 'east', 'south', 'west']) {
      const source = Array.isArray(lanes[lane]) ? lanes[lane] : [];
      normalized[lane] = source.map((vehicle, index) => {
        const vehicleId = vehicle?.vehicleId || vehicle?.id || `video-${lane}-${index + 1}`;
        const vehicleType = vehicle?.vehicleType || 'car';
        return {
          vehicleId,
          vehicleType,
          laneId: lane,
          position: Number(vehicle?.position || 0),
          spawnedAt: Number(vehicle?.spawnedAt || now)
        };
      });
    }

    return normalized;
  }

  function logSeedEvents(seedLanes) {
    const ts = Date.now();
    for (const lane of ['north', 'east', 'south', 'west']) {
      const vehicles = Array.isArray(seedLanes[lane]) ? seedLanes[lane] : [];
      for (const vehicle of vehicles) {
        logEvent({
          eventType: 'vehicle_added',
          vehicleId: vehicle.vehicleId,
          vehicleType: vehicle.vehicleType,
          laneId: lane,
          timestamp: ts,
          payload: { source: 'video_state_extractor' }
        });
      }
    }
  }

  const handleFileChange = (e) => {
    setSelectedFile(e.target.files[0]);
    setError(null);
  };

  const handleUpload = async () => {
    if (!selectedFile) return;
    setUploading(true);
    setError(null);
    try {
      const result = await uploadVideo(selectedFile);
      const resolvedSessionId = result.session_id || result.sessionId || null;
      if (!resolvedSessionId) {
        setError('Session ID missing in upload response.');
        setUploading(false);
        return;
      }
      setSessionId(resolvedSessionId);
      setVideoPath(result.video_path);
      setMode('video');
    } catch (err) {
      setError('Upload failed. Please try again.');
    }
    setUploading(false);
  };

  const handleStartJob = async () => {
    try {
      await startVideoJob(sessionId, videoPath);
      setJobStarted(true);
      intervalRef.current = setInterval(async () => {
        try {
          const status = await getJobStatus(sessionId);
          setJobStatus(status);
          setProgress(status.progress || 0);
          if (status.status === 'completed' || status.status === 'failed') {
            clearInterval(intervalRef.current);
          }
        } catch (err) {
          clearInterval(intervalRef.current);
          setError('Failed to get job status.');
        }
      }, 2000);
    } catch (err) {
      setError('Failed to start processing.');
    }
  };

  return (
    <div className="dashboard">
      <AppSidebar />

      <main className="content">
        <header className="content-header">
          <h1>Video Pipeline</h1>
          <p>Upload a video, run processing, and open a comparison dashboard.</p>
        </header>

        <Section title="Upload Video" className="upload-panel">

          <div className="form-row">
            <label className="input-label">Select Video File</label>
            <input
              type="file"
              accept="video/*"
              onChange={handleFileChange}
              className="input-control"
            />
          </div>

          {!sessionId && (
            <Button
              onClick={handleUpload}
              disabled={!selectedFile || uploading}
            >
              {uploading ? 'Uploading...' : 'Upload Video'}
            </Button>
          )}

          {sessionId && !jobStarted && (
            <div className="status-stack">
              <p className="muted-text">Upload successful. Session: {sessionId.slice(0, 8)}...</p>
              <Button onClick={handleStartJob}>Start Processing</Button>
            </div>
          )}

          {jobStarted && jobStatus && (
            <div className="status-stack">
              <p className="muted-text">Status: <strong>{jobStatus.status?.toUpperCase()}</strong></p>
              <progress className="progress-bar" value={progress} max={100} />
              <p className="muted-text">{progress}% complete</p>

              {jobStatus.status === 'completed' && (
                <Button
                  onClick={() => {
                    const resolvedSessionId = jobStatus.session_id || jobStatus.sessionId || null;
                    if (!resolvedSessionId) {
                      setError('Session ID missing after preprocessing. Cannot start simulation.');
                      return;
                    }

                    const timerDuration = Number(jobStatus.timer_duration || 60);
                    const seededLanes = normalizeSimulationLanes(jobStatus.simulation_state);

                    resetStore();
                    setTimer(timerDuration);
                    setSessionId(resolvedSessionId);
                    setSessionIdStore(resolvedSessionId);
                    setMode('video');
                    setSignalPhases([]);
                    setTotalVehiclesCrossed(0);
                    updateVehiclePositions(seededLanes);
                    logSeedEvents(seededLanes);
                    startSimulation();
                    navigate('/');
                  }}
                >
                  Start Simulation
                </Button>
              )}

              {jobStatus.status === 'failed' && (
                <p className="alert alert-high">{jobStatus.error_message || 'Processing failed'}</p>
              )}
            </div>
          )}

          {error && <p className="alert alert-high">{error}</p>}

          <Button variant="secondary" onClick={() => navigate('/')}>Back To Simulator</Button>
        </Section>
      </main>
    </div>
  );
}
