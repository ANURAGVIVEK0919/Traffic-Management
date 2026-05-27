import { useEffect, useRef, useState } from 'react';
import { useSimulationStore } from '../state/simulationStore';
import { fetchLiveCounts, logSignalPhase, createSession, submitEventLog } from '../services/api';
import { getModelDuration, explainDecision } from '../services/signalApi';
import { buildLaneSnapshot } from '../utils/simulationUtils';
import { moveVehicles, checkVehicleCrossing } from '../utils/vehicleUtils';
import { generateVehicleId } from '../utils/simulationUtils';
import { useNavigate, useSearchParams } from 'react-router-dom';
import AppSidebar from '../components/layout/AppSidebar';
import Card from '../components/ui/Card';
import Button from '../components/ui/Button';
import Section from '../components/ui/Section';
import TimerControl from '../components/controls/TimerControl';
import LLMConfigBox from '../components/simulation/LLMConfigBox';
import LLMExplanationPanel from '../components/dashboard/LLMExplanationPanel';
import './dashboard.css';

const VEHICLE_TYPES = ['car', 'bike', 'ambulance', 'truck', 'bus'];
const LANE_ORDER = ['north', 'east', 'south', 'west'];
const MIN_GREEN = 5;
const MAX_GREEN = 25;
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
  const [plannedDuration, setPlannedDuration] = useState(8);
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
  const [interruptedRemainingTime, setInterruptedRemainingTime] = useState(0);
  const [v2iBeacons, setV2IBeacons] = useState([]);
  const [v2iAlertLane, setV2IAlertLane] = useState(null);
  const [v2iSimulations, setV2ISimulations] = useState([]);
  const v2iSimulationsRef = useRef([]);

  const status = useSimulationStore(state => state.status);
  const mode = useSimulationStore(state => state.mode);
  const lanes = useSimulationStore(state => state.lanes);
  const lightStates = useSimulationStore(state => state.lightStates);
  const timeRemaining = useSimulationStore((state) => state.timeRemaining);
  const videoSchedule = useSimulationStore((state) => state.videoSchedule);
  const decrementTimer = useSimulationStore((state) => state.decrementTimer);
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
  const interruptedRemainingTimeRef = useRef(0);
  const v2iAlertLaneRef = useRef(null);

  // LLM-configurable controller params (set via LLMConfigBox)
  const controllerConfigRef = useRef({
    max_green: MAX_GREEN,
    min_green: MIN_GREEN,
    yellow_time: YELLOW_TIME,
    ambulance_preempt_immediately: true,
  });

  const [latestExplanation, setLatestExplanation] = useState(null);
  const [explanationLog, setExplanationLog] = useState([]);

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
    interruptedRemainingTimeRef.current = interruptedRemainingTime;
  }, [interruptedRemainingTime]);

  useEffect(() => {
    v2iAlertLaneRef.current = v2iAlertLane;
  }, [v2iAlertLane]);

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
      if (!sessionId) return;
      try {
        const response = await fetch(`http://localhost:8000/simulation/live-counts/${sessionId}`);
        if (response.ok) {
          const data = await response.json();
          if (cancelled) return;
          // Support both array [N,S,E,W] and object {north, south...}
          if (Array.isArray(data)) {
            setBackendCounts({
              north: data[0] || 0,
              south: data[1] || 0,
              east: data[2] || 0,
              west: data[3] || 0
            });
          } else {
            setBackendCounts(data);
          }
        }
      } catch (err) {
        console.warn("Polling failed:", err);
      }
    };

    syncLiveCounts();
    const pollInterval = setInterval(syncLiveCounts, 3000); // Fallback poll every 3s

    if (!sessionId) return;

    const ws = new WebSocket(`ws://localhost:8000/ws/simulation/${sessionId}`);

    ws.onopen = () => {
      console.log("✅ WebSocket connected:", sessionId);
    };

    ws.onmessage = (event) => {
      console.log("WS RECEIVED:", event.data);
      const data = JSON.parse(event.data);

      let raw = data?.lane_counts;
      let counts = { north: 0, south: 0, east: 0, west: 0 };
      if (Array.isArray(raw)) {
        counts = {
          north: Number(raw[0] || 0),
          south: Number(raw[1] || 0),
          east: Number(raw[2] || 0),
          west: Number(raw[3] || 0)
        };
      }

      if (!cancelled) {
        setBackendCounts(counts);
        if (data.active_lane) {
          updateLightStates(data.active_lane);
          setCurrentGreenLane(data.active_lane);

          // Fix: Update plannedDuration from backend adaptive decision
          // RULE: Cannot extend or change duration if already in Yellow Phase
          if (data.duration && !isYellowPhaseRef.current) {
            setPlannedDuration(Number(data.duration));
            setPhaseStartTick(tickCount);
          }
        }
      }
    };

    ws.onerror = (err) => {
      console.error("❌ WebSocket error:", err);
    };

    ws.onclose = () => {
      console.warn("⚠️ WebSocket closed. Reconnecting...");
      setTimeout(() => {
        if (!cancelled) window.location.reload();
      }, 2000);
    };

    return () => {
      cancelled = true;
      ws.close();
      clearInterval(pollInterval);
    };
  }, [mode, sessionId]);

  // V2I Hub Polling
  useEffect(() => {
    if (status !== 'running') return;

    const pollV2I = async () => {
      try {
        const response = await fetch('http://localhost:8000/v2i/active');
        const active = await response.json();
        
        setV2IBeacons(active);

        if (active.length > 0) {
          // Find the most urgent beacon
          const urgent = [...active].sort((a, b) => a.eta - b.eta)[0];
          setV2IAlertLane(urgent.lane);
        } else {
          setV2IAlertLane(null);
        }
      } catch (err) {
        console.warn('V2I Hub polling failed:', err);
      }
    };

    const interval = setInterval(pollV2I, 1000);
    return () => clearInterval(interval);
  }, [status]);

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
    
    // Log as event for backend metrics
    logEvent({
      eventType: 'signal_phase',
      laneId: previousLane,
      timestamp: Date.now(),
      payload: {
        lane: previousLane,
        duration: duration
      }
    });

    setCurrentGreenLane(newLane);
    currentGreenLaneRef.current = newLane;
    setPhaseStartTick(simulatedTick);
    phaseStartTickRef.current = simulatedTick;
    updateLightStates(newLane);
  }

  async function runTick() {
    if (!tickingRef.current) return;

    console.log("TIMER UPDATE", timeRemainingRef.current);

    try {
      if (timeRemainingRef.current <= 0) {
        freezeSimulation();
        tickingRef.current = false;
        return;
      }

      const simulatedTick = tickCountRef.current + 1;
      let activeGreenLane = currentGreenLaneRef.current;

      // --- V2I Ambulance Simulation Updates ---
      const updatedSims = [];
      for (const sim of v2iSimulationsRef.current) {
        if (sim.status === 'crossed') {
          updatedSims.push(sim);
          continue;
        }

        let newDist = sim.distance;
        let newSpeed = sim.speed;
        let newStatus = sim.status;
        let newWaitTime = sim.waitTime;
        let newQueuePos = sim.queuePosition;

        if (newStatus === 'approaching') {
          newDist = Math.max(0, newDist - newSpeed);
          if (newDist === 0) {
            newStatus = 'waiting';
            newSpeed = 0.0;
            newQueuePos = lanesRef.current[sim.lane]?.length || 0;
            console.log(`📡 V2I Ambulance ${sim.vehicle_id} reached intersection. Queue: ${newQueuePos}`);
          }
        }

        if (newStatus === 'waiting') {
          newSpeed = 0.0;
          const isLaneGreen = (activeGreenLane === sim.lane && !isYellowPhaseRef.current);

          // If the light is green and we have a queue, vehicles clear at 1 vehicle/sec
          if (isLaneGreen && newQueuePos > 0) {
            newQueuePos = Math.max(0, newQueuePos - 1);
          }

          if (isLaneGreen && newQueuePos === 0) {
            newStatus = 'crossed';
            newDist = 0.0;
            console.log(`📡 V2I Ambulance ${sim.vehicle_id} crossing after waiting ${newWaitTime}s!`);
            logEvent({
              eventType: 'vehicle_crossed',
              vehicleId: sim.vehicle_id,
              vehicleType: 'ambulance',
              laneId: sim.lane,
              timestamp: Date.now(),
              payload: { isVirtual: true }
            });
          } else {
            newWaitTime += 1;
          }
        }

        const updatedSim = {
          ...sim,
          distance: newDist,
          speed: newSpeed,
          status: newStatus,
          waitTime: newWaitTime,
          queuePosition: newQueuePos
        };
        updatedSims.push(updatedSim);

        // Update the backend beacon
        if (newStatus !== 'crossed') {
          fetch('http://localhost:8000/v2i/beacon', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              vehicle_id: sim.vehicle_id,
              lane: sim.lane,
              distance: newDist,
              speed: newSpeed
            })
          }).catch(e => console.warn('V2I update failed:', e));
        }
      }
      v2iSimulationsRef.current = updatedSims;
      setV2ISimulations(updatedSims);

      const elapsedTimeBeforeScan = Math.max(0, simulatedTick - phaseStartTickRef.current);
      if (!emergencyPhaseRef.current && activeGreenLane) {
        let detected = null;
        for (const lane of LANE_ORDER) {
          if (lane !== activeGreenLane && lanesRef.current[lane].some(v => v.vehicleType === 'ambulance')) {
            detected = lane;
            break;
          }
        }
        
        // V2I EARLY WARNING: If V2I detects an ambulance before camera sees it
        if (!detected && v2iAlertLaneRef.current && v2iAlertLaneRef.current !== activeGreenLane) {
          detected = v2iAlertLaneRef.current;
          console.log(`📡 V2I EARLY WARNING: Pre-empting for ${detected.toUpperCase()}`);
        }

        if (detected) {
          setEmergencyPhase('pre-empting');
          emergencyPhaseRef.current = 'pre-empting';
          setEmergencyLane(detected);
          emergencyLaneRef.current = detected;
          setInterruptedLane(activeGreenLane);
          interruptedLaneRef.current = activeGreenLane;
          
          // CONTEXT SAVE: Save how much green time was left for this lane
          const remaining = Math.max(0, plannedDurationRef.current - elapsedTimeBeforeScan);
          setInterruptedRemainingTime(remaining);
          interruptedRemainingTimeRef.current = remaining;

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

      const elapsedTime = Math.max(0, simulatedTick - phaseStartTickRef.current);
      updateLightStates(activeGreenLane);

      const updatedLanes = moveVehicles(lanesRef.current, {
        north: activeGreenLane === 'north' ? 'green' : 'red',
        south: activeGreenLane === 'south' ? 'green' : 'red',
        east: activeGreenLane === 'east' ? 'green' : 'red',
        west: activeGreenLane === 'west' ? 'green' : 'red'
      }, elapsedTime);

      const lanesAfterCross = { north: [], east: [], south: [], west: [] };
      let removedVehiclesThisTick = 0;
      let crossedTimeThisTick = 0;

      for (const lane of LANE_ORDER) {
        // Implementation of Saturation Flow (C5): 
        // Even in green, vehicles only cross when they physically reach the intersection.
        // We allow up to 1 vehicle per second to cross (Saturation flow approximation).
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
            const crossTime = mode === 'video'
              ? vehicle.spawnedAt + (Date.now() - (vehicle.realSpawnedAt || Date.now()))
              : Date.now();
            logEvent({
              eventType: 'vehicle_crossed',
              vehicleId: vehicle.vehicleId,
              vehicleType: vehicle.vehicleType,
              laneId: vehicle.laneId,
              timestamp: crossTime,
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
          const hasV2IAlert = v2iAlertLaneRef.current === activeGreenLane;
          
          if (!hasAmbulance && !hasV2IAlert && elapsedTime >= MIN_GREEN) {
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
          if (elapsedTime >= INITIAL_CYCLE_TIME && !isYellowPhaseRef.current) {
            setIsYellowPhase(true);
            isYellowPhaseRef.current = true;
          }
          if (elapsedTime >= INITIAL_CYCLE_TIME + YELLOW_TIME) {
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
            // Math formula as fallback
            const cfg = controllerConfigRef.current;
            const mathFallback = Math.max(
              Math.min(currentVehiclesTime + crossedTimeThisPhaseRef.current, cfg.max_green),
              cfg.min_green
            );

            // Build traffic state for model
            const waitTimes = {};
            for (const lane of LANE_ORDER) {
              const vehicles = lanesAfterCross[lane] || [];
              const totalWait = vehicles.reduce((acc, v) => acc + Math.max(0, (Date.now() - (v.spawnedAt || Date.now())) / 1000), 0);
              waitTimes[lane] = vehicles.length > 0 ? totalWait / vehicles.length : 0;
            }
            const ambulanceState = {};
            for (const lane of LANE_ORDER) {
              ambulanceState[lane] = (lanesAfterCross[lane] || []).some(v => v.vehicleType === 'ambulance');
            }

            // Non-blocking model call — updates planned duration when resolved
            getModelDuration(
              {
                lane_counts: laneCounts,
                wait_times: waitTimes,
                ambulance: ambulanceState,
                current_lane: activeGreenLane,
                elapsed_time: elapsedTime,
              },
              mathFallback
            ).then(modelTarget => {
              // Respect LLM-configured max/min from controllerConfigRef
              const bounded = Math.max(
                controllerConfigRef.current.min_green,
                Math.min(controllerConfigRef.current.max_green, modelTarget)
              );
              // C6: Only update if yellow phase has NOT started
              if (!isYellowPhaseRef.current && plannedDurationRef.current !== bounded) {
                setPlannedDuration(bounded);
                plannedDurationRef.current = bounded;
              }
            });

            // Apply math fallback immediately (model will override when ready)
            target = mathFallback;
            if (plannedDurationRef.current !== target) { setPlannedDuration(target); plannedDurationRef.current = target; }
          }

          if (elapsedTime >= target && !isYellowPhaseRef.current) {
            setIsYellowPhase(true);
            isYellowPhaseRef.current = true;
          }
          if (elapsedTime >= target + YELLOW_TIME) {
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

          // Async: fetch LLM explanation for this lane switch (non-blocking)
          (() => {
            const waitTimes = {};
            const ambulanceState = {};
            for (const lane of LANE_ORDER) {
              const vehicles = lanesAfterCross[lane] || [];
              const totalWait = vehicles.reduce((acc, v) => acc + Math.max(0, (Date.now() - (v.spawnedAt || Date.now())) / 1000), 0);
              waitTimes[lane] = vehicles.length > 0 ? totalWait / vehicles.length : 0;
              ambulanceState[lane] = vehicles.some(v => v.vehicleType === 'ambulance');
            }
            explainDecision(
              { lane_counts: laneCounts, wait_times: waitTimes, ambulance: ambulanceState, current_lane: activeGreenLane },
              duration
            ).then(explanation => {
              if (explanation) {
                const entry = { lane: activeGreenLane, duration, explanation, timestamp: Date.now() };
                setLatestExplanation(entry);
                setExplanationLog(prev => [entry, ...prev].slice(0, 10));
              }
            });
          })();

          setIsYellowPhase(false);
          isYellowPhaseRef.current = false;

          let nextDuration = initialCyclesDoneRef.current < 3 ? INITIAL_CYCLE_TIME : MIN_GREEN;

          // We use local dynamic queue-clearing duration logic directly
          if (mode === 'video' && initialCyclesDoneRef.current >= 3) {
            nextDuration = MIN_GREEN; // Will be scaled up dynamically by target recalculation
          }

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
            
            // Apply Restored Timer if we were interrupted
            if (interruptedRemainingTimeRef.current > 0) {
              const restoredTime = Math.max(MIN_GREEN, interruptedRemainingTimeRef.current);
              setPlannedDuration(restoredTime);
              plannedDurationRef.current = restoredTime;
              setInterruptedRemainingTime(0);
              interruptedRemainingTimeRef.current = 0;
            }

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
      console.error("Simulation Tick Error:", err);
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
    setV2ISimulations([]);
    v2iSimulationsRef.current = [];
    tickingRef.current = true;
  }

  function handleConfigUpdate(params) {
    console.log('LLM Config Update:', params);
    controllerConfigRef.current = {
      ...controllerConfigRef.current,
      ...params
    };
  }

  useEffect(() => {
    let interval = null;

    if (status === 'running') {
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
    if (mode === 'video') return;

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

  async function handleTriggerV2I(laneId) {
    try {
      const vid = `V2I-AMB-${Math.floor(Math.random() * 1000)}`;
      
      const newSim = {
        vehicle_id: vid,
        lane: laneId,
        distance: 400.0,
        speed: 15.0,
        status: 'approaching',
        waitTime: 0,
        spawnedAt: Date.now(),
        queuePosition: null
      };
      
      v2iSimulationsRef.current = [...v2iSimulationsRef.current, newSim];
      setV2ISimulations(v2iSimulationsRef.current);

      await fetch('http://localhost:8000/v2i/beacon', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          vehicle_id: vid,
          lane: laneId,
          distance: 400.0,
          speed: 15.0
        })
      });
      console.log(`📡 Triggered V2I beacon for ${laneId}`);

      // Log as virtual vehicle for metrics
      logEvent({
        eventType: 'vehicle_added',
        vehicleId: vid,
        vehicleType: 'ambulance',
        laneId: laneId,
        timestamp: Date.now(),
        payload: { isVirtual: true }
      });
    } catch (err) {
      console.error('Failed to trigger V2I beacon:', err);
    }
  }

  // --- AUTOMATED DEMO MODE START ---
  // This logic only runs if ?demo=true is in the URL!
  // Manual mode at standard /simulation is completely unaffected.
  // Periodic State Sync for Video Mode
  useEffect(() => {
    if (mode !== 'video' || status !== 'running' || !sessionId) return;

    const syncInterval = setInterval(async () => {
      const currentLaneCounts = {
        north: (lanes['north'] || []).length,
        south: (lanes['south'] || []).length,
        east: (lanes['east'] || []).length,
        west: (lanes['west'] || []).length,
      };

      try {
        await submitEventLog(sessionId, [{
          eventType: 'state_sync',
          timestamp: Date.now(),
          payload: { lane_counts: currentLaneCounts }
        }]);
      } catch (err) {
        console.warn('Failed to sync state to backend:', err);
      }
    }, 2000);

    return () => clearInterval(syncInterval);
  }, [mode, status, sessionId, lanes]);

  useEffect(() => {
    if (mode !== 'video' || status !== 'running') return;

    console.log("🎬 [PLAYBACK] Starting video schedule playback...");

    // Create a local copy to track which events have fired
    const schedule = [...videoSchedule].map(e => ({ ...e, fired: false }));
    const startTime = Date.now();

    const interval = setInterval(() => {
      const elapsedMs = Date.now() - startTime;

      schedule.forEach(event => {
        if (!event.fired && event.timestamp <= elapsedMs) {
          event.fired = true;

          const vehicle = {
            vehicleId: event.vehicleId,
            vehicleType: event.vehicleType,
            laneId: event.laneId,
            spawnedAt: event.timestamp,
            realSpawnedAt: Date.now(),
            position: 0
          };

          logEvent(event);
          addVehicleToLane(vehicle, event.laneId);
        }
      });

      if (timeRemainingRef.current <= 0) clearInterval(interval);
    }, 100);

    return () => clearInterval(interval);
  }, [mode, status, videoSchedule]);

  useEffect(() => {
    if (mode === 'video') return;
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

    if (mode === 'video') return;

    if (isAutoRunMode && status === 'running') {
      if (scenarioMode === 'master') {
        const schedule = [
          // 1. Initialization (0-40s)
          { t: 3000, drops: Array(2).fill({ lane: 'north', type: 'car' }) },
          { t: 8000, drops: Array(5).fill({ lane: 'west', type: 'bike' }) },
          // Prep for Dynamic Scaling (North getting loaded before cycle 5)
          { t: 25000, drops: Array(8).fill({ lane: 'north', type: 'car' }) },
          // 2. Dynamic Upscaling in Green Phase (Drop at 43s, extends North's target)
          { t: 43000, drops: Array(2).fill({ lane: 'north', type: 'bus' }) },
          // 3. Yellow Phase Freezing (Drop at 53s during Yellow lock, forces queueing)
          { t: 53000, drops: Array(4).fill({ lane: 'north', type: 'car' }) },
          // 4. Instant Preemption (Drop ambulance in South while West is actively green)
          { t: 62000, drops: [{ lane: 'south', type: 'ambulance' }] },
          // 5. Normal traffic resumes heavily just to prove resumption works
          { t: 80000, drops: Array(5).fill({ lane: 'east', type: 'car' }) }
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
    const count = vehicles.length;

    // Use backend perception counts in video mode, otherwise use 2D simulation state
    const displayCount = mode === 'video' ? (backendCounts[laneId] || 0) : count;
    
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
          <p className="lane-count">{displayCount} Waiting</p>
          {isActive ? <p className="lane-crossed">{crossedThisPhase} Crossed This Phase</p> : null}
        </div>

        <div className="lane-actions">
          {VEHICLE_TYPES.map(type => (
            <button
              key={type}
              className="vehicle-icon-btn"
              disabled={mode === 'video'}
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
          <h1>{mode === 'video' ? 'Video Analysis Dashboard' : 'Traffic Control Simulation'}</h1>
          <p>
            {mode === 'video'
              ? 'Monitoring live traffic metrics from processed video stream'
              : 'Manage lane vehicles and monitor live Adaptive Traffic Management decisions'}
          </p>
        </header>

        <Section className="simulation-topbar">
          <div className="timer-chip">
            <span>Time Remaining</span>
            <strong>{Number(timeRemaining || 0).toFixed(1)}s</strong>
          </div>

          <Button variant="secondary" onClick={() => navigate('/upload')}>
            Upload Video
          </Button>
        </Section>

        <div className="simulation-layout">
          <div className="simulation-main-col">
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

            {v2iBeacons.length > 0 && (
              <Section title="🛰️ V2I Emergency GPS Radar (Digital Siren Enabled)" className="v2i-radar-section">
                <div className="v2i-siren-overlay">
                  <div className="siren-pulse-ring"></div>
                  <div className="siren-pulse-ring-slow"></div>
                </div>
                <div className="v2i-beacons-list">
                  {v2iBeacons.map(beacon => {
                    const sim = v2iSimulations.find(s => s.vehicle_id === beacon.vehicle_id);
                    const isWaiting = sim?.status === 'waiting';
                    const isCrossed = sim?.status === 'crossed';
                    
                    let etaText = `${beacon.eta}s`;
                    let distText = `${Math.round(beacon.distance)}m`;
                    let statusText = 'Approaching Intersection (GPS Siren Active)';
                    
                    if (isWaiting) {
                      etaText = `🛑 WAITING`;
                      distText = `0m (Wait: ${sim.waitTime}s)`;
                      statusText = sim.queuePosition > 0 
                        ? `Stopped behind ${sim.queuePosition} vehicle(s) in queue`
                        : 'Waiting at stopline for green light';
                    } else if (isCrossed) {
                      etaText = `✅ PASSED`;
                      distText = `Passed`;
                      statusText = 'Intersection cleared successfully!';
                    }
                    
                    return (
                      <div key={beacon.vehicle_id} className={`v2i-beacon-item ${isWaiting ? 'v2i-alert-waiting' : isCrossed ? 'v2i-alert-passed' : 'v2i-alert-active'}`}>
                        <div className="v2i-beacon-info">
                          <span className="v2i-beacon-id">📡 GPS: {beacon.vehicle_id}</span>
                          <span className="v2i-beacon-lane">{beacon.lane.toUpperCase()} LANE EMERGENCY APPROACH</span>
                          <p className="v2i-beacon-subtitle" style={{ fontSize: '0.85rem', color: '#a0aec0', margin: '4px 0 0 0' }}>
                            {statusText}
                          </p>
                        </div>
                        <div className="v2i-beacon-stats">
                          <div className="v2i-stat">
                            <label>Distance (GPS)</label>
                            <span style={{ color: isWaiting ? '#fc8181' : isCrossed ? '#68d391' : 'inherit' }}>{distText}</span>
                          </div>
                          <div className="v2i-stat">
                            <label>Siren ETA</label>
                            <span className={`v2i-eta-highlight ${isWaiting ? 'pulse-text-red' : isCrossed ? 'text-green' : 'pulse-text'}`} style={{ color: isWaiting ? '#fc8181' : isCrossed ? '#68d391' : '#f6ad55' }}>
                              {etaText}
                            </span>
                          </div>
                        </div>
                        <div className="v2i-progress">
                          <div 
                            className={`v2i-progress-fill ${isWaiting ? 'bg-red' : isCrossed ? 'bg-green' : 'siren-bg'}`} 
                            style={{ 
                              width: isCrossed ? '100%' : `${Math.max(0, (1 - (sim?.distance || beacon.distance) / 400) * 100)}%`,
                              backgroundColor: isWaiting ? '#fc8181' : isCrossed ? '#48bb78' : undefined
                            }} 
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
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

            {(status === 'setup' || status === 'running') && (
              <Section title="🚨 Emergency Intervention (V2I Simulation)">
                <p className="muted-text">Simulate an Ambulance approaching from 400m via GPS/Siren Beacon:</p>
                <div className="v2i-trigger-grid">
                  {LANE_ORDER.map(lane => (
                    <Button key={lane} variant="secondary" onClick={() => handleTriggerV2I(lane)}>
                      📡 {lane.toUpperCase()} (400m)
                    </Button>
                  ))}
                </div>
              </Section>
            )}

            {status === 'setup' && (
              <Section title="Intelligence Configuration">
                <TimerControl />
                <div style={{ marginTop: '2rem' }}>
                  <LLMConfigBox onConfigUpdate={handleConfigUpdate} />
                </div>
              </Section>
            )}

            {status === 'placement' && (
              <Section>
                <div style={{ marginBottom: '2rem' }}>
                  <LLMConfigBox onConfigUpdate={handleConfigUpdate} />
                </div>
                <Button onClick={handleStart}>Start Simulation</Button>
              </Section>
            )}
          </div>

          <div className="simulation-sidebar-col">
            <LLMExplanationPanel explanationLog={explanationLog} />
          </div>
        </div>
      </main>
    </div>
  );
}