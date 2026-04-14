import { useEffect, useRef, useState } from 'react';
import { useSimulationStore } from '../state/simulationStore';
import { fetchLiveCounts, fetchRLDecision, logSignalPhase } from '../services/api';
import { buildLaneSnapshot } from '../utils/simulationUtils';
import { moveVehicles, checkVehicleCrossing } from '../utils/vehicleUtils';
import { generateVehicleId } from '../utils/simulationUtils';
import { useNavigate } from 'react-router-dom';
import TimerControl from '../components/controls/TimerControl';

import AppSidebar from '../components/layout/AppSidebar';
import Card from '../components/ui/Card';
import Button from '../components/ui/Button';
import Section from '../components/ui/Section';
import './dashboard.css';

const VEHICLE_TYPES = ['car', 'bike', 'ambulance', 'truck', 'bus'];
const LANE_ORDER = ['north', 'east', 'south', 'west'];
const MIN_SAFE_TIME = 2;
const NORMAL_SWITCH_TIME = 8;
const MAX_GREEN_TIME = 12;

const VEHICLE_ICONS = {
  car: '🚗',
  bike: '🚲',
  ambulance: '🚑',
  truck: '🚚',
  bus: '🚌'
};

export default function SimulationPage() {
  const [lastDecision, setLastDecision] = useState(null);
  const [currentGreenLane, setCurrentGreenLane] = useState(null);
  const [phaseStartTick, setPhaseStartTick] = useState(0);
  const [signalPhases, setSignalPhases] = useState([]);
  const [decisionDebugLogs, setDecisionDebugLogs] = useState([]);
  const [backendCounts, setBackendCounts] = useState({
    north: 0,
    south: 0,
    east: 0,
    west: 0
  });

  const status = useSimulationStore(state => state.status);
  const mode = useSimulationStore(state => state.mode);
  const lanes = useSimulationStore(state => state.lanes);
  const lightStates = useSimulationStore(state => state.lightStates);
  const timeRemaining = useSimulationStore(state => state.timeRemaining);
  const sessionId = useSimulationStore(state => state.sessionId);

  const startSimulation = useSimulationStore(state => state.startSimulation);
  const setMode = useSimulationStore(state => state.setMode);
  const freezeSimulation = useSimulationStore(state => state.freezeSimulation);
  const updateLightStates = useSimulationStore(state => state.updateLightStates);
  const updateVehiclePositions = useSimulationStore(state => state.updateVehiclePositions);
  const logEvent = useSimulationStore(state => state.logEvent);
  const addSignalPhase = useSimulationStore(state => state.addSignalPhase);
  const setSignalPhasesStore = useSimulationStore(state => state.setSignalPhases);
  const incrementTotalVehiclesCrossed = useSimulationStore(state => state.incrementTotalVehiclesCrossed);
  const setTotalVehiclesCrossed = useSimulationStore(state => state.setTotalVehiclesCrossed);
  const decrementTimer = useSimulationStore(state => state.decrementTimer);
  const incrementTick = useSimulationStore(state => state.incrementTick);
  const addVehicleToLane = useSimulationStore(state => state.addVehicleToLane);
  const tickCount = useSimulationStore(state => state.tickCount);

  const tickingRef = useRef(false);
  const timeRemainingRef = useRef(timeRemaining);
  const lanesRef = useRef(lanes);
  const lightStatesRef = useRef(lightStates);
  const tickCountRef = useRef(tickCount);
  const currentGreenLaneRef = useRef(currentGreenLane);
  const phaseStartTickRef = useRef(phaseStartTick);

  const navigate = useNavigate();

  useEffect(() => {
    timeRemainingRef.current = timeRemaining;
  }, [timeRemaining]);

  useEffect(() => {
    lanesRef.current = lanes;
  }, [lanes]);

  useEffect(() => {
    lightStatesRef.current = lightStates;
  }, [lightStates]);

  useEffect(() => {
    tickCountRef.current = tickCount;
  }, [tickCount]);

  useEffect(() => {
    currentGreenLaneRef.current = currentGreenLane;
  }, [currentGreenLane]);

  useEffect(() => {
    phaseStartTickRef.current = phaseStartTick;
  }, [phaseStartTick]);

  useEffect(() => {
    if (mode !== 'video') {
      return undefined;
    }

    let cancelled = false;

    const syncLiveCounts = async () => {
      try {
        const dataCounts = await fetchLiveCounts();
        const countsArray = dataCounts || [0, 0, 0, 0];
        if (cancelled) {
          return;
        }

        const mappedCounts = {
          north: Number(countsArray[0] || 0),
          south: Number(countsArray[1] || 0),
          east: Number(countsArray[2] || 0),
          west: Number(countsArray[3] || 0),
        };

        console.log('STATE:', mappedCounts);
        setBackendCounts(mappedCounts);
      } catch (err) {
        if (!cancelled) {
          setBackendCounts({
            north: 0,
            south: 0,
            east: 0,
            west: 0
          });
        }
      }
    };

    syncLiveCounts();
    const interval = setInterval(syncLiveCounts, 1000);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [mode]);

  useEffect(() => {
    console.log('CURRENT MODE:', mode);
  }, [mode]);

  function getActiveGreenLane(lightMap) {
    for (const lane of LANE_ORDER) {
      if (lightMap?.[lane] === 'green') return lane;
    }
    return null;
  }

  function getLaneCounts(laneMap) {
    return {
      north: laneMap.north.length,
      east: laneMap.east.length,
      south: laneMap.south.length,
      west: laneMap.west.length
    };
  }

  function getFallbackLane(currentLane, laneCounts) {
    const sortedCandidates = LANE_ORDER
      .filter((lane) => lane !== currentLane)
      .sort((a, b) => laneCounts[b] - laneCounts[a]);

    const busiestLane = sortedCandidates.find((lane) => laneCounts[lane] > 0);
    if (busiestLane) return busiestLane;

    const currentIndex = LANE_ORDER.indexOf(currentLane);
    if (currentIndex === -1) return 'north';
    return LANE_ORDER[(currentIndex + 1) % LANE_ORDER.length];
  }

  function applyLaneSwitch(newLane, simulatedTick, duration) {
    const previousLane = currentGreenLaneRef.current;
    if (!newLane || !previousLane || newLane === previousLane) return;

    const phase = { lane: previousLane, duration };

    setSignalPhases((prev) => [
      ...prev,
      phase
    ]);
    addSignalPhase(phase);
    setCurrentGreenLane(newLane);
    currentGreenLaneRef.current = newLane;
    setPhaseStartTick(simulatedTick);
    phaseStartTickRef.current = simulatedTick;
    updateLightStates(newLane);
  }

  async function runTick() {
    if (!tickingRef.current) return;

    // In video mode, RL decisions are produced by the backend video pipeline.
    // Skip frontend simulation ticks to avoid posting stale/empty local lane counts.
    if (mode === 'video') {
      return;
    }

    try {
      if (timeRemainingRef.current <= 0) {
        freezeSimulation();
        tickingRef.current = false;
        return;
      }

      const snapshot = buildLaneSnapshot(lanesRef.current);
      const payload = {
        ...snapshot,
        timestamp: Date.now() / 1000,
        active_green_lane: getActiveGreenLane(lightStatesRef.current)
      };

      const decision = await fetchRLDecision(payload);

      const rlSuggestedLane = LANE_ORDER.includes(decision?.lane)
        ? decision.lane
        : 'north';

      const simulatedTick = tickCountRef.current + 1;
      let activeGreenLane = currentGreenLaneRef.current;

      if (!activeGreenLane) {
        activeGreenLane = getActiveGreenLane(lightStatesRef.current) || rlSuggestedLane;
        setCurrentGreenLane(activeGreenLane);
        currentGreenLaneRef.current = activeGreenLane;
        setPhaseStartTick(simulatedTick);
        phaseStartTickRef.current = simulatedTick;
      }

      setLastDecision(decision);
      setDecisionDebugLogs((prev) => [
        ...prev,
        {
          tick: simulatedTick,
          lane: activeGreenLane,
          duration: Number(decision?.duration ?? 0),
          strategy: decision?.debug?.strategy || 'n/a'
        }
      ].slice(-25));

      updateLightStates(activeGreenLane);

      const updatedLanes = moveVehicles(lanesRef.current, {
        north: activeGreenLane === 'north' ? 'green' : 'red',
        south: activeGreenLane === 'south' ? 'green' : 'red',
        east: activeGreenLane === 'east' ? 'green' : 'red',
        west: activeGreenLane === 'west' ? 'green' : 'red'
      });

      const lanesAfterCross = { north: [], east: [], south: [], west: [] };
      let removedVehiclesThisTick = 0;

      for (const lane of LANE_ORDER) {
        for (const vehicle of updatedLanes[lane]) {
          if (lane !== activeGreenLane) {
            lanesAfterCross[lane].push(vehicle);
            continue;
          }

          const cross = checkVehicleCrossing(vehicle);

          if (cross.crossed) {
            removedVehiclesThisTick += 1;
            logEvent({
              eventType: 'vehicle_crossed',
              vehicleId: vehicle.vehicleId,
              vehicleType: vehicle.vehicleType,
              laneId: vehicle.laneId,
              timestamp: Date.now(),
              payload: {}
            });
          } else {
            lanesAfterCross[lane].push(vehicle);
          }
        }
      }

      updateVehiclePositions(lanesAfterCross);
      if (removedVehiclesThisTick > 0) {
        incrementTotalVehiclesCrossed(removedVehiclesThisTick);
      }

      const laneCounts = getLaneCounts(lanesAfterCross);
      const allLanesEmpty = LANE_ORDER.every((lane) => laneCounts[lane] <= 1);
      const vehicleCount = laneCounts[activeGreenLane] ?? 0;
      const elapsedTime = Math.max(0, simulatedTick - phaseStartTickRef.current);
      const totalVehiclesCrossedAfterTick = useSimulationStore.getState().totalVehiclesCrossed;

      const canEarlyExit = elapsedTime >= MIN_SAFE_TIME && vehicleCount <= 1 && !allLanesEmpty;
      const canNormalSwitch = elapsedTime >= NORMAL_SWITCH_TIME && rlSuggestedLane !== activeGreenLane;
      const mustForceSwitch = elapsedTime >= MAX_GREEN_TIME;

      let shouldSwitch = false;
      let reason = '';
      let newLane = activeGreenLane;

      if (canEarlyExit) {
        shouldSwitch = true;
        reason = 'EARLY_EXIT';
      } else if (canNormalSwitch) {
        shouldSwitch = true;
        reason = 'NORMAL_SWITCH';
      } else if (mustForceSwitch) {
        shouldSwitch = true;
        reason = 'MAX_TIMEOUT';
      }

      if (shouldSwitch) {
        if (rlSuggestedLane !== activeGreenLane) {
          newLane = rlSuggestedLane;
        } else {
          newLane = getFallbackLane(activeGreenLane, laneCounts);
        }

        if (newLane !== activeGreenLane) {
          const duration = elapsedTime;
          if (sessionId && activeGreenLane) {
            try {
              await logSignalPhase(sessionId, activeGreenLane, duration);
            } catch (error) {
              console.warn('Failed to log signal phase:', error);
            }
          }
          applyLaneSwitch(newLane, simulatedTick, duration);
        }
      }

      decrementTimer(1);
      incrementTick();

      if (timeRemainingRef.current - 1 <= 0) {
        freezeSimulation();
        tickingRef.current = false;
      }

    } catch (err) {
    }
  }

  function handleStart() {
    if (mode !== 'video') {
      setMode('simulation');
    }
    startSimulation();
    setSignalPhases([]);
    setSignalPhasesStore([]);
    setDecisionDebugLogs([]);
    setCurrentGreenLane(null);
    setPhaseStartTick(0);
    currentGreenLaneRef.current = null;
    phaseStartTickRef.current = 0;
    setTotalVehiclesCrossed(0);
    tickingRef.current = true;
  }

  useEffect(() => {
    let interval = null;

    if (status === 'running' && mode !== 'video') {
      tickingRef.current = true;
      interval = setInterval(runTick, 1000);
    } else {
      tickingRef.current = false;
    }

    return () => {
      if (interval) clearInterval(interval);
      tickingRef.current = false;
    };
  }, [status, mode]);

  useEffect(() => {
    if (status === 'completed') {
      navigate('/loading');
    }
  }, [status, navigate]);

  function handleAddVehicle(laneId, vehicleType) {
    const vehicleId = generateVehicleId(vehicleType, laneId);

    const vehicle = {
      vehicleId,
      vehicleType,
      laneId,
      spawnedAt: Date.now(),
      position: 0
    };

    logEvent({
      eventType: 'vehicle_added',
      vehicleId,
      vehicleType,
      laneId,
      timestamp: vehicle.spawnedAt,
      payload: {}
    });

    addVehicleToLane(vehicle, laneId);
  }

  function LaneCard({ laneId }) {
    const isActive = lightStates[laneId] === 'green';
    const vehicles = lanes[laneId] || [];
    const count = mode === 'video' ? Number(backendCounts[laneId] || 0) : vehicles.length;
    console.log(`LANE ${laneId}:`, backendCounts[laneId]);

    return (
      <Card className={`lane-card ${isActive ? 'lane-card-active' : ''}`}>
        <div className="lane-card-header">
          <h3>{laneId.toUpperCase()}</h3>
          <span className={`lane-status ${isActive ? 'lane-status-active' : 'lane-status-stopped'}`}>
            {isActive ? 'ACTIVE' : 'STOPPED'}
          </span>
        </div>

        <p className="lane-count">{count} Vehicles</p>

        <div className="lane-actions">
          {VEHICLE_TYPES.map(type => (
            <button
              key={type}
              className="vehicle-icon-btn"
              onClick={() => handleAddVehicle(laneId, type)}
            >
              {VEHICLE_ICONS[type]}
            </button>
          ))}
        </div>
      </Card>
    );
  }

  const timerPercent = Math.max(0, Math.min(100, (timeRemaining / 60) * 100));
  const activePhaseDuration = currentGreenLane ? Math.max(0, tickCount - phaseStartTick) : 0;
  const displayedSignalPhases = currentGreenLane
    ? [...signalPhases, { lane: currentGreenLane, duration: activePhaseDuration, active: true }]
    : signalPhases;

  useEffect(() => {
    setSignalPhasesStore(
      displayedSignalPhases.map(({ active, ...phase }) => phase)
    );
  }, [displayedSignalPhases, setSignalPhasesStore]);

  return (
    <div className="dashboard">
      <AppSidebar />

      <main className="content">
        <header className="content-header">
          <h1>Traffic Control Simulation</h1>
          <p>Manage lane vehicles and monitor live RL decisions</p>
        </header>

        <Section className="simulation-topbar">
          <div className="timer-chip">
            <span>Time Remaining</span>
            <strong>{timeRemaining}s</strong>
          </div>

          <Button variant="secondary" onClick={() => navigate('/upload')}>
            Upload Video
          </Button>
        </Section>

        <Section title="Simulation Progress">
          <progress className="progress-bar" value={timerPercent} max={100} />
        </Section>

        <section className="lane-grid">
          {LANE_ORDER.map(laneId => (
            <LaneCard key={laneId} laneId={laneId} />
          ))}
        </section>

        <Section title="Actual Signal Durations (Simulation)">
          {displayedSignalPhases.length === 0 ? (
            <p className="muted-text">No signal phases recorded yet.</p>
          ) : (
            <div className="table-wrap">
              <table className="decision-table">
                <thead>
                  <tr>
                    <th>Lane</th>
                    <th className="align-right">Actual Duration (s)</th>
                  </tr>
                </thead>
                <tbody>
                  {displayedSignalPhases.map((phase, index) => (
                    <tr key={`${phase.lane}-${index}`}>
                      <td>{String(phase.lane || '--').toUpperCase()}</td>
                      <td className="align-right">
                        {Number(phase.duration || 0).toFixed(1)}
                        {phase.active ? ' (active)' : ''}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Section>

        {status === 'running' && lastDecision && (
          <Section title="Debug Panel (Simulation Only)">
            <p><strong>Lane:</strong> {lastDecision.lane}</p>
            <p><strong>Duration:</strong> {lastDecision.duration ?? '--'}s</p>
            <p><strong>Strategy:</strong> {lastDecision?.debug?.strategy}</p>
            {decisionDebugLogs.length > 0 && (
              <div className="table-wrap">
                <table className="decision-table">
                  <thead>
                    <tr>
                      <th className="align-right">Tick</th>
                      <th>Lane</th>
                      <th className="align-right">Duration (s)</th>
                      <th>Strategy</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...decisionDebugLogs].reverse().map((log, idx) => (
                      <tr key={`${log.tick}-${idx}`}>
                        <td className="align-right">{log.tick}</td>
                        <td>{String(log.lane || '--').toUpperCase()}</td>
                        <td className="align-right">{Number(log.duration || 0).toFixed(1)}</td>
                        <td>{log.strategy}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Section>
        )}

        {status === 'setup' && (
          <Section title="Setup Timer">
            <TimerControl />
          </Section>
        )}

        {status === 'placement' && (
          <Section>
            <Button onClick={handleStart}>Start Simulation</Button>
          </Section>
        )}
      </main>
    </div>
  );
}