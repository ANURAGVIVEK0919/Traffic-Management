import { useEffect, useRef, useState } from 'react';
import { useSimulationStore } from '../state/simulationStore';
import { fetchLiveCounts, logSignalPhase, createSession } from '../services/api';
import { buildLaneSnapshot } from '../utils/simulationUtils';
import { moveVehicles, checkVehicleCrossing } from '../utils/vehicleUtils';
import { generateVehicleId } from '../utils/simulationUtils';
import { useNavigate, useSearchParams } from 'react-router-dom';
import TimerControl from '../components/controls/TimerControl';

import AppSidebar from '../components/layout/AppSidebar';
import Card from '../components/ui/Card';
import Button from '../components/ui/Button';
import Section from '../components/ui/Section';
import './dashboard.css';

const VEHICLE_TYPES = ['car', 'bike', 'ambulance', 'truck', 'bus'];
const LANE_ORDER = ['north', 'west', 'south', 'east'];
const MIN_GREEN = 10;
const MAX_GREEN = 30;
const YELLOW_TIME = 5;
const INITIAL_CYCLE_TIME = 10;

const VEHICLE_TIME_MULTIPLIERS = {
  car: 1.0,
  bike: 0.5,
  ambulance: 1.0,
  truck: 2.0,
  bus: 2.5
};

const VEHICLE_ICONS = {
  car: '🚗',
  bike: '🚲',
  ambulance: '🚑',
  truck: '🚚',
  bus: '🚌'
};

export default function SimulationPage() {
  const [currentGreenLane, setCurrentGreenLane] = useState(null);
  const [phaseStartTick, setPhaseStartTick] = useState(0);
  const [signalPhases, setSignalPhases] = useState([]);

  const [initialCyclesDone, setInitialCyclesDone] = useState(0);
  const [isYellowPhase, setIsYellowPhase] = useState(false);
  const [plannedDuration, setPlannedDuration] = useState(10);
  const [crossedThisPhase, setCrossedThisPhase] = useState(0);
  const [backendCounts, setBackendCounts] = useState({
    north: 0,
    south: 0,
    east: 0,
    west: 0
  });

  const [emergencyPhase, setEmergencyPhase] = useState(null);
  const [emergencyLane, setEmergencyLane] = useState(null);
  const [interruptedLane, setInterruptedLane] = useState(null);

  const status = useSimulationStore(state => state.status);
  const mode = useSimulationStore(state => state.mode);
  const lanes = useSimulationStore(state => state.lanes);
  const lightStates = useSimulationStore(state => state.lightStates);
  const timeRemaining = useSimulationStore(state => state.timeRemaining);
  const sessionId = useSimulationStore(state => state.sessionId);

  const startSimulation = useSimulationStore(state => state.startSimulation);
  const setMode = useSimulationStore(state => state.setMode);
  const setTimer = useSimulationStore(state => state.setTimer);
  const setSessionId = useSimulationStore(state => state.setSessionId);

  const [searchParams] = useSearchParams();
  const isDemoMode = searchParams.get('demo') === 'true';
  const scenarioMode = searchParams.get('scenario');
  const isAutoRunMode = isDemoMode || scenarioMode === 'high_traffic' || scenarioMode === 'emergency' || scenarioMode === 'master';
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
  const initialCyclesDoneRef = useRef(initialCyclesDone);
  const isYellowPhaseRef = useRef(isYellowPhase);
  const plannedDurationRef = useRef(plannedDuration);
  const crossedThisPhaseRef = useRef(crossedThisPhase);
  const crossedTimeThisPhaseRef = useRef(0);

  const emergencyPhaseRef = useRef(emergencyPhase);
  const emergencyLaneRef = useRef(emergencyLane);
  const interruptedLaneRef = useRef(interruptedLane);

  const navigate = useNavigate();

  useEffect(() => {
    emergencyPhaseRef.current = emergencyPhase;
  }, [emergencyPhase]);

  useEffect(() => {
    emergencyLaneRef.current = emergencyLane;
  }, [emergencyLane]);

  useEffect(() => {
    interruptedLaneRef.current = interruptedLane;
  }, [interruptedLane]);

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
    initialCyclesDoneRef.current = initialCyclesDone;
  }, [initialCyclesDone]);

  useEffect(() => {
    isYellowPhaseRef.current = isYellowPhase;
  }, [isYellowPhase]);

  useEffect(() => {
    plannedDurationRef.current = plannedDuration;
  }, [plannedDuration]);

  useEffect(() => {
    crossedThisPhaseRef.current = crossedThisPhase;
  }, [crossedThisPhase]);

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

    // In video mode, Adaptive Traffic Management decisions are produced by the backend video pipeline.
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

      const simulatedTick = tickCountRef.current + 1;
      let activeGreenLane = currentGreenLaneRef.current;

      const elapsedTimeBeforeScan = Math.max(0, simulatedTick - phaseStartTickRef.current);
      if (!emergencyPhaseRef.current && activeGreenLane) {
        let detected = null;
        for (const lane of LANE_ORDER) {
          if (lane !== activeGreenLane && lanesRef.current[lane].some(v => v.vehicleType === 'ambulance')) {
            detected = lane;
            break;
          }
        }
        if (detected) {
          setEmergencyPhase('pre-empting');
          emergencyPhaseRef.current = 'pre-empting';
          setEmergencyLane(detected);
          emergencyLaneRef.current = detected;
          setInterruptedLane(activeGreenLane);
          interruptedLaneRef.current = activeGreenLane;

          if (!isYellowPhaseRef.current) {
            setIsYellowPhase(true);
            isYellowPhaseRef.current = true;
            const target = elapsedTimeBeforeScan + YELLOW_TIME;
            setPlannedDuration(target);
            plannedDurationRef.current = target;
          }
        }
      }

      if (!activeGreenLane) {
        activeGreenLane = getActiveGreenLane(lightStatesRef.current) || 'north';
        setCurrentGreenLane(activeGreenLane);
        currentGreenLaneRef.current = activeGreenLane;
        setPhaseStartTick(simulatedTick);
        phaseStartTickRef.current = simulatedTick;
        setInitialCyclesDone(0);
        initialCyclesDoneRef.current = 0;
        setIsYellowPhase(false);
        isYellowPhaseRef.current = false;
        setPlannedDuration(INITIAL_CYCLE_TIME);
        plannedDurationRef.current = INITIAL_CYCLE_TIME;
        setCrossedThisPhase(0);
        crossedThisPhaseRef.current = 0;
        crossedTimeThisPhaseRef.current = 0;
      }

      updateLightStates(activeGreenLane);

      const updatedLanes = moveVehicles(lanesRef.current, {
        north: activeGreenLane === 'north' ? 'green' : 'red',
        south: activeGreenLane === 'south' ? 'green' : 'red',
        east: activeGreenLane === 'east' ? 'green' : 'red',
        west: activeGreenLane === 'west' ? 'green' : 'red'
      });

      const lanesAfterCross = { north: [], east: [], south: [], west: [] };
      let removedVehiclesThisTick = 0;
      let crossedTimeThisTick = 0;

      for (const lane of LANE_ORDER) {
        let allowedToCross = lane === activeGreenLane ? 1 : 0;

        for (const vehicle of updatedLanes[lane]) {
          if (lane !== activeGreenLane) {
            lanesAfterCross[lane].push(vehicle);
            continue;
          }

          const cross = checkVehicleCrossing(vehicle);

          if (cross.crossed && allowedToCross > 0) {
            removedVehiclesThisTick += 1;
            allowedToCross -= 1;
            crossedTimeThisTick += (VEHICLE_TIME_MULTIPLIERS[vehicle.vehicleType] || 1);
            logEvent({
              eventType: 'vehicle_crossed',
              vehicleId: vehicle.vehicleId,
              vehicleType: vehicle.vehicleType,
              laneId: vehicle.laneId,
              timestamp: Date.now(),
              payload: {}
            });
          } else {
            if (cross.crossed) {
              // Peg it back at the stopline so it waits in queue for the next second!
              vehicle.position = 2.0;
            }
            lanesAfterCross[lane].push(vehicle);
          }
        }
      }

      updateVehiclePositions(lanesAfterCross);
      if (removedVehiclesThisTick > 0) {
        incrementTotalVehiclesCrossed(removedVehiclesThisTick);
        setCrossedThisPhase(prev => prev + removedVehiclesThisTick);
        crossedThisPhaseRef.current += removedVehiclesThisTick;
        crossedTimeThisPhaseRef.current += crossedTimeThisTick;
      }

      const laneCounts = getLaneCounts(lanesAfterCross);
      const vehicleCount = laneCounts[activeGreenLane] ?? 0;
      const elapsedTime = Math.max(0, simulatedTick - phaseStartTickRef.current);

      let shouldSwitch = false;
      let newLane = activeGreenLane;

      if (emergencyPhaseRef.current) {
        if (emergencyPhaseRef.current === 'pre-empting') {
          if (elapsedTime >= plannedDurationRef.current) {
            shouldSwitch = true;
            newLane = emergencyLaneRef.current;
            setEmergencyPhase('active');
            emergencyPhaseRef.current = 'active';
          }
        } else if (emergencyPhaseRef.current === 'active') {
          const hasAmbulance = lanesAfterCross[activeGreenLane].some(v => v.vehicleType === 'ambulance');
          if (!hasAmbulance && elapsedTime >= MIN_GREEN) {
            setEmergencyPhase('recovering');
            emergencyPhaseRef.current = 'recovering';
            if (!isYellowPhaseRef.current) {
              setIsYellowPhase(true);
              isYellowPhaseRef.current = true;
            }
            const target = elapsedTime + YELLOW_TIME;
            setPlannedDuration(target);
            plannedDurationRef.current = target;
          } else {
            const target = elapsedTime + YELLOW_TIME + 2;
            if (plannedDurationRef.current !== target) {
              setPlannedDuration(target);
              plannedDurationRef.current = target;
            }
          }
        } else if (emergencyPhaseRef.current === 'recovering') {
          if (elapsedTime >= plannedDurationRef.current) {
            shouldSwitch = true;
            newLane = interruptedLaneRef.current || LANE_ORDER[(LANE_ORDER.indexOf(activeGreenLane) + 1) % LANE_ORDER.length];
          }
        }
      } else {
        if (initialCyclesDoneRef.current < 4) {
          if (plannedDurationRef.current !== INITIAL_CYCLE_TIME) { setPlannedDuration(INITIAL_CYCLE_TIME); plannedDurationRef.current = INITIAL_CYCLE_TIME; }
          if (elapsedTime >= INITIAL_CYCLE_TIME - YELLOW_TIME && !isYellowPhaseRef.current) {
            setIsYellowPhase(true);
            isYellowPhaseRef.current = true;
          }
          if (elapsedTime >= INITIAL_CYCLE_TIME) {
            shouldSwitch = true;
            setInitialCyclesDone(prev => prev + 1);
            initialCyclesDoneRef.current += 1;
          }
        } else {
          let target = plannedDurationRef.current;
          if (!isYellowPhaseRef.current) {
            let currentVehiclesTime = 0;
            for (const v of (lanesAfterCross[activeGreenLane] || [])) {
              currentVehiclesTime += (VEHICLE_TIME_MULTIPLIERS[v.vehicleType] || 1);
            }
            target = Math.max(Math.min(currentVehiclesTime + crossedTimeThisPhaseRef.current, MAX_GREEN), MIN_GREEN);
            if (plannedDurationRef.current !== target) { setPlannedDuration(target); plannedDurationRef.current = target; }
          }

          if (elapsedTime >= target - YELLOW_TIME && !isYellowPhaseRef.current) {
            setIsYellowPhase(true);
            isYellowPhaseRef.current = true;
          }
          if (elapsedTime >= target) {
            shouldSwitch = true;
          }
        }
      }

      if (shouldSwitch) {
        if (!emergencyPhaseRef.current) {
          const currentIndex = LANE_ORDER.indexOf(activeGreenLane);
          newLane = LANE_ORDER[(currentIndex + 1) % LANE_ORDER.length];
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
          setIsYellowPhase(false);
          isYellowPhaseRef.current = false;
          const nextDuration = initialCyclesDoneRef.current < 3 ? INITIAL_CYCLE_TIME : MIN_GREEN;
          setPlannedDuration(nextDuration);
          plannedDurationRef.current = nextDuration;
          setCrossedThisPhase(0);
          crossedThisPhaseRef.current = 0;
          crossedTimeThisPhaseRef.current = 0;

          if (emergencyPhaseRef.current === 'recovering') {
            setEmergencyPhase(null);
            emergencyPhaseRef.current = null;
            setEmergencyLane(null);
            emergencyLaneRef.current = null;
            setInterruptedLane(null);
            interruptedLaneRef.current = null;
          }
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
    setCurrentGreenLane(null);
    setPhaseStartTick(0);
    phaseStartTickRef.current = 0;
    setInitialCyclesDone(0);
    initialCyclesDoneRef.current = 0;
    setIsYellowPhase(false);
    isYellowPhaseRef.current = false;
    setPlannedDuration(INITIAL_CYCLE_TIME);
    plannedDurationRef.current = INITIAL_CYCLE_TIME;
    setCrossedThisPhase(0);
    crossedThisPhaseRef.current = 0;
    crossedTimeThisPhaseRef.current = 0;
    setEmergencyPhase(null);
    emergencyPhaseRef.current = null;
    setEmergencyLane(null);
    emergencyLaneRef.current = null;
    setInterruptedLane(null);
    interruptedLaneRef.current = null;
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

  // --- AUTOMATED DEMO MODE START ---
  // This logic only runs if ?demo=true is in the URL!
  // Manual mode at standard /simulation is completely unaffected.
  useEffect(() => {
    if (isAutoRunMode && status === 'setup') {
      console.log("[Auto Run] Initializing automated setup...");
      setTimer(180);

      const initializeDemo = async () => {
        try {
          const result = await createSession(180);
          console.log("[Auto Run] Session Created:", result.session_id);
          setSessionId(result.session_id);

          setTimeout(() => {
            handleStart();
          }, 1000);
        } catch (e) {
          console.error("[Auto Run] Auto setup failed:", e);
        }
      };

      initializeDemo();
    }
  }, [isAutoRunMode, status]);

  useEffect(() => {
    let spawnInterval = null;
    let emergencyInterval = null;

    if (isAutoRunMode && status === 'running') {
      if (scenarioMode === 'master') {
        const schedule = [
          // 1. Initialization (0-40s)
          { t: 3000, drops: Array(2).fill({lane: 'north', type: 'car'}) },
          { t: 8000, drops: Array(5).fill({lane: 'west', type: 'bike'}) }, 
          // Prep for Dynamic Scaling (North getting loaded before cycle 5)
          { t: 25000, drops: Array(8).fill({lane: 'north', type: 'car'}) },
          // 2. Dynamic Upscaling in Green Phase (Drop at 43s, extends North's target)
          { t: 43000, drops: Array(2).fill({lane: 'north', type: 'bus'}) },
          // 3. Yellow Phase Freezing (Drop at 53s during Yellow lock, forces queueing)
          { t: 53000, drops: Array(4).fill({lane: 'north', type: 'car'}) },
          // 4. Instant Preemption (Drop ambulance in South while West is actively green)
          { t: 62000, drops: [{lane: 'south', type: 'ambulance'}] },
          // 5. Normal traffic resumes heavily just to prove resumption works
          { t: 80000, drops: Array(5).fill({lane: 'east', type: 'car'}) }
        ];

        const startTime = Date.now();
        spawnInterval = setInterval(() => {
          if (timeRemainingRef.current <= 0) return;
          const elapsed = Date.now() - startTime;
          schedule.forEach(evt => {
            if (!evt.fired && elapsed >= evt.t) {
              evt.fired = true;
              evt.drops.forEach(d => handleAddVehicle(d.lane, d.type));
            }
          });
        }, 500);
      } else {
        const spawnRate = scenarioMode === 'high_traffic' ? 800 : 1500;

        spawnInterval = setInterval(() => {
          if (timeRemainingRef.current <= 0) return;
          const lanes = ['north', 'south', 'east', 'west'];
          let types = ['car', 'car', 'car', 'bike', 'truck'];

          if (scenarioMode === 'high_traffic') {
            types = ['car', 'car', 'car', 'truck', 'bus', 'bike', 'car'];
          } else if (isDemoMode) {
            types = ['car', 'car', 'car', 'car', 'bike', 'bike', 'truck', 'bus'];
          } else if (scenarioMode === 'emergency') {
            types = ['car', 'car', 'car', 'bike'];
          }

          const randomLane = lanes[Math.floor(Math.random() * lanes.length)];
          const randomType = types[Math.floor(Math.random() * types.length)];

          handleAddVehicle(randomLane, randomType);

          if (Math.random() > 0.5) {
            setTimeout(() => {
              const randomType2 = types[Math.floor(Math.random() * types.length)];
              handleAddVehicle(randomLane, randomType2);
            }, 600);
          }
        }, spawnRate);

        if (scenarioMode === 'emergency') {
          emergencyInterval = setInterval(() => {
            if (timeRemainingRef.current <= 0) return;
            const lanes = ['north', 'south', 'east', 'west'];
            const randomLane = lanes[Math.floor(Math.random() * lanes.length)];
            handleAddVehicle(randomLane, 'ambulance');
          }, 35000);
        }
      }
    }
    return () => {
      if (spawnInterval) clearInterval(spawnInterval);
      if (emergencyInterval) clearInterval(emergencyInterval);
    };
  }, [isAutoRunMode, isDemoMode, scenarioMode, status]);
  // --- AUTOMATED DEMO MODE END ---

  function LaneCard({ laneId }) {
    const isActive = lightStates[laneId] === 'green';
    const vehicles = lanes[laneId] || [];
    const count = mode === 'video' ? Number(backendCounts[laneId] || 0) : vehicles.length;

    const isThisLaneYellow = isActive && isYellowPhase;
    const timeToSwitch = Math.max(0, plannedDuration - (tickCount - phaseStartTick));

    return (
      <Card className={`lane-card ${isActive ? 'lane-card-active' : ''} ${isThisLaneYellow ? 'lane-card-yellow' : ''}`}>
        <div className="lane-card-header">
          <h3>{laneId.toUpperCase()}</h3>
          <span className={`lane-status ${isActive ? (isThisLaneYellow ? 'lane-status-yellow' : 'lane-status-active') : 'lane-status-stopped'}`}>
            {isActive ? (isThisLaneYellow ? `🟡 SWITCHING IN ${timeToSwitch}S` : 'ACTIVE') : 'STOPPED'}
          </span>
        </div>

        <div className="lane-stats-wrap">
          <p className="lane-count">{count} Waiting</p>
          {isActive ? <p className="lane-crossed">{crossedThisPhase} Crossed This Phase</p> : null}
        </div>

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
          <p>Manage lane vehicles and monitor live Adaptive Traffic Management decisions</p>
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

        {emergencyPhase && (
          <Section className={`status-banner status-warning emergency-banner-${emergencyPhase}`}>
            {emergencyPhase === 'pre-empting' && <h3 style={{ color: 'white', margin: 0 }}>🚨 Emergency Vehicle Detected in {String(emergencyLane).toUpperCase()}! Switching in {Math.max(0, plannedDuration - (tickCount - phaseStartTick))}s</h3>}
            {emergencyPhase === 'active' && <h3 style={{ color: 'white', margin: 0 }}>🚑 Emergency Override Active for {String(emergencyLane).toUpperCase()}. Waiting for vehicle to pass...</h3>}
            {emergencyPhase === 'recovering' && <h3 style={{ color: 'white', margin: 0 }}>✅ Emergency Cleared! Resuming normal cycle in {Math.max(0, plannedDuration - (tickCount - phaseStartTick))}s...</h3>}
          </Section>
        )}

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