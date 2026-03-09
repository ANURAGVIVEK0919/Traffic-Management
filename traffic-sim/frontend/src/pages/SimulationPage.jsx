
import { useEffect, useRef } from 'react';
import { useSimulationStore } from '../state/simulationStore';
import { fetchRLDecision } from '../services/api';
import { buildLaneSnapshot } from '../utils/simulationUtils';
import { moveVehicles, checkVehicleCrossing } from '../utils/vehicleUtils';
import { generateVehicleId } from '../utils/simulationUtils';
import { useNavigate } from 'react-router-dom';
import TimerControl from '../components/controls/TimerControl';

const VEHICLE_TYPES = ['car', 'bike', 'ambulance', 'truck', 'bus'];
const LANE_ORDER = ['north', 'east', 'south', 'west'];

export default function SimulationPage() {
  const status = useSimulationStore(state => state.status);
  const lanes = useSimulationStore(state => state.lanes);
  const lightStates = useSimulationStore(state => state.lightStates);
  const timeRemaining = useSimulationStore(state => state.timeRemaining);
  const startSimulation = useSimulationStore(state => state.startSimulation);
  const freezeSimulation = useSimulationStore(state => state.freezeSimulation);
  const updateLightStates = useSimulationStore(state => state.updateLightStates);
  const updateVehiclePositions = useSimulationStore(state => state.updateVehiclePositions);
  const logEvent = useSimulationStore(state => state.logEvent);
  const decrementTimer = useSimulationStore(state => state.decrementTimer);
  const incrementTick = useSimulationStore(state => state.incrementTick);
  const addVehicleToLane = useSimulationStore(state => state.addVehicleToLane);

  const tickingRef = useRef(false);
  const timeRemainingRef = useRef(timeRemaining);
  const lanesRef = useRef(lanes);
  const navigate = useNavigate();

  useEffect(() => {
    timeRemainingRef.current = timeRemaining;
  }, [timeRemaining]);

  // Keep lanesRef in sync with lanes state
  useEffect(() => {
    lanesRef.current = lanes;
  }, [lanes]);

  async function runTick() {
    if (!tickingRef.current) return;
    if (timeRemainingRef.current <= 0) {
      freezeSimulation();
      tickingRef.current = false;
      return;
    }
    // Use lanesRef.current for RL snapshot and vehicle movement
    const snapshot = buildLaneSnapshot(lanesRef.current);
    console.log('Lane snapshot sent to RL:', JSON.stringify(snapshot));
    const decision = await fetchRLDecision(snapshot);
    console.log('RL decision:', decision);
    updateLightStates(decision.lane);
    const updatedLanes = moveVehicles(lanesRef.current, {
      north: decision.lane === 'north' ? 'green' : 'red',
      south: decision.lane === 'south' ? 'green' : 'red',
      east: decision.lane === 'east' ? 'green' : 'red',
      west: decision.lane === 'west' ? 'green' : 'red'
    });
    const lanesAfterCross = { north: [], east: [], south: [], west: [] };
    for (const lane of LANE_ORDER) {
      for (const vehicle of updatedLanes[lane]) {
        const cross = checkVehicleCrossing(vehicle);
        if (cross.crossed) {
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
    decrementTimer(1);
    incrementTick();
    const newTime = timeRemainingRef.current - 1;
    if (newTime <= 0) {
      freezeSimulation();
      tickingRef.current = false;
    }
  }

  function handleStart() {
    startSimulation();
    tickingRef.current = true;
  }

  useEffect(() => {
    let interval = null;
    if (status === 'running') {
      tickingRef.current = true;
      interval = setInterval(() => {
        if (tickingRef.current) runTick();
      }, 1000);
    }
    return () => {
      if (interval) clearInterval(interval);
      tickingRef.current = false;
    };
  }, [status]);

  useEffect(() => {
    if (status === 'completed') {
      navigate('/loading');
    }
  }, [status, navigate]);

  // Handler for adding vehicle
  function handleAddVehicle(laneId, vehicleType) {
    const vehicleId = generateVehicleId(vehicleType, laneId);
    const vehicle = {
      vehicleId,
      vehicleType,
      laneId,
      spawnedAt: Date.now(),
      position: 0
    };
    // Log vehicle_added event
    logEvent({
      eventType: 'vehicle_added',
      vehicleId,
      vehicleType,
      laneId,
      timestamp: vehicle.spawnedAt,
      payload: {}
    });
    // Add vehicle to lane
    addVehicleToLane(vehicle, laneId);
    // Debug lanesRef after vehicle added
    console.log('Vehicle added, lanesRef:', JSON.stringify(lanesRef.current));
  }

  // Lane card UI
  function LaneCard({ laneId }) {
    const isActive = lightStates[laneId] === 'green';
    const cardStyle = {
      background: 'rgba(18,24,38,0.95)',
      borderRadius: 16,
      boxShadow: isActive
        ? '0 0 24px 6px #00ffae, 0 0 8px 2px #00ffe7 inset'
        : '0 0 8px 2px #ff2d2d inset',
      border: isActive
        ? '2px solid #00ffae'
        : '2px solid #ff2d2d',
      animation: isActive ? 'pulseGreen 1.2s infinite' : 'none',
      padding: 24,
      margin: 16,
      width: 260,
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      fontFamily: 'Rajdhani, monospace',
      position: 'relative',
      transition: 'box-shadow 0.3s, border 0.3s',
    };
    const badgeStyle = {
      fontFamily: 'Share Tech Mono, monospace',
      fontSize: 18,
      padding: '6px 18px',
      borderRadius: 16,
      background: isActive ? 'linear-gradient(90deg,#00ffae,#00ffe7)' : 'linear-gradient(90deg,#ff2d2d,#ff5c5c)',
      color: '#0a0e1a',
      fontWeight: 'bold',
      boxShadow: isActive ? '0 0 12px 2px #00ffae' : '0 0 8px 2px #ff2d2d',
      marginBottom: 8,
      marginTop: 8,
      letterSpacing: 2,
      textShadow: isActive ? '0 0 8px #00ffe7' : '0 0 4px #ff2d2d',
    };
    const vehicleCountStyle = {
      fontSize: 22,
      color: '#00ffe7',
      fontFamily: 'Share Tech Mono, monospace',
      marginBottom: 8,
      textShadow: '0 0 8px #00ffe7',
    };
    const laneNameStyle = {
      fontFamily: 'Share Tech Mono, monospace',
      fontSize: 24,
      color: '#fff',
      marginTop: 8,
      letterSpacing: 2,
      textShadow: '0 0 8px #00ffe7',
    };
    const iconButtonStyle = {
      background: '#0a0e1a',
      color: '#00ffe7',
      border: '2px solid #00ffe7',
      borderRadius: 8,
      fontSize: 22,
      padding: '8px 12px',
      margin: '4px',
      cursor: 'pointer',
      boxShadow: '0 0 8px 2px #00ffe7',
      transition: 'background 0.2s, color 0.2s',
      fontFamily: 'Rajdhani, monospace',
    };
    const icons = {
      car: '🚗',
      bike: '🚲',
      ambulance: '🚑',
      truck: '🚚',
      bus: '🚌',
    };
    return (
      <div style={cardStyle}>
        <span style={laneNameStyle}>{laneId.toUpperCase()}</span>
        <span style={badgeStyle}>{isActive ? 'ACTIVE' : 'STOPPED'}</span>
        <div style={vehicleCountStyle}>{(lanes[laneId] || []).length} Vehicles</div>
        <div style={{ marginTop: 12, display: 'flex', flexWrap: 'wrap', gap: 8, justifyContent: 'center' }}>
          {VEHICLE_TYPES.map(type => (
            <button key={type} style={iconButtonStyle} onClick={() => handleAddVehicle(laneId, type)} title={type.charAt(0).toUpperCase() + type.slice(1)}>
              {icons[type]}
            </button>
          ))}
        </div>
      </div>
    );
  }

  // Google Fonts
  if (typeof window !== 'undefined') {
    const link1 = document.createElement('link');
    link1.href = 'https://fonts.googleapis.com/css?family=Share+Tech+Mono:400&display=swap';
    link1.rel = 'stylesheet';
    document.head.appendChild(link1);
    const link2 = document.createElement('link');
    link2.href = 'https://fonts.googleapis.com/css?family=Rajdhani:400,700&display=swap';
    link2.rel = 'stylesheet';
    document.head.appendChild(link2);
  }

  // Glowing ring timer animation
  const timerRingStyle = {
    width: 180,
    height: 180,
    borderRadius: '50%',
    border: '8px solid #00ffe7',
    boxShadow: '0 0 32px 8px #00ffe7',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    margin: '0 auto',
    marginBottom: 32,
    position: 'relative',
    animation: 'glowRing 1.5s infinite alternate',
  };
  const timerTextStyle = {
    fontFamily: 'Share Tech Mono, monospace',
    fontSize: 48,
    color: '#00ffe7',
    textShadow: '0 0 16px #00ffe7',
    letterSpacing: 2,
    fontWeight: 700,
    position: 'absolute',
    left: '50%',
    top: '50%',
    transform: 'translate(-50%, -50%)',
  };
  const gridStyle = {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gridTemplateRows: '1fr 1fr',
    gap: 32,
    justifyContent: 'center',
    alignItems: 'center',
    margin: '0 auto',
    maxWidth: 600,
    marginBottom: 32,
  };
  const mainBgStyle = {
    minHeight: '100vh',
    background: '#0a0e1a',
    backgroundImage: 'repeating-linear-gradient(135deg, rgba(255,255,255,0.02) 0px, rgba(255,255,255,0.02) 1px, transparent 1px, transparent 20px)',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'flex-start',
    padding: 0,
    fontFamily: 'Rajdhani, monospace',
  };
  const headerStyle = {
    fontFamily: 'Share Tech Mono, monospace',
    fontSize: 36,
    color: '#00ffe7',
    textShadow: '0 0 16px #00ffe7',
    marginTop: 32,
    marginBottom: 24,
    letterSpacing: 4,
    fontWeight: 700,
    textAlign: 'center',
  };
  const timerBarStyle = {
  width: '80%',
  height: 18,
  background: 'linear-gradient(90deg,#00ffae,#00ffe7)',
  borderRadius: 12,
  margin: '32px auto',
  boxShadow: '0 0 16px #00ffe7',
  overflow: 'hidden',
};
  const timerBarFillStyle = {
    height: '100%',
    background: '#0a0e1a',
    borderRadius: 12,
    transition: 'width 0.5s',
    width: `${Math.max(0, Math.min(100, (timeRemaining / 60) * 100))}%`,
  };

  // Keyframes for glowing ring and lane pulse
  const styleSheet = document.createElement('style');
  styleSheet.innerHTML = `
    @keyframes glowRing {
      0% { box-shadow: 0 0 32px 8px #00ffe7; }
      100% { box-shadow: 0 0 64px 16px #00ffe7; }
    }
    @keyframes pulseGreen {
      0% { box-shadow: 0 0 24px 6px #00ffae, 0 0 8px 2px #00ffe7 inset; }
      50% { box-shadow: 0 0 48px 12px #00ffae, 0 0 16px 4px #00ffe7 inset; }
      100% { box-shadow: 0 0 24px 6px #00ffae, 0 0 8px 2px #00ffe7 inset; }
    }
  `;
  if (typeof window !== 'undefined' && !document.head.querySelector('style[data-simpage]')) {
    styleSheet.setAttribute('data-simpage', 'true');
    document.head.appendChild(styleSheet);
  }

  return (
    <div style={mainBgStyle}>
      <div style={headerStyle}>Traffic Control System</div>
      {(status === 'setup' || status === 'placement' || status === 'running') && (
        <div style={timerRingStyle}>
          <span style={timerTextStyle}>{timeRemaining}</span>
        </div>
      )}
      <div style={gridStyle}>
        {LANE_ORDER.map(laneId => (
          <LaneCard key={laneId} laneId={laneId} />
        ))}
      </div>
      <div style={timerBarStyle}>
        <div style={timerBarFillStyle}></div>
      </div>
      {status === 'setup' && <TimerControl />}
      {status === 'placement' && (
        <button
          style={{
            fontFamily: 'Share Tech Mono, monospace',
            fontSize: 22,
            color: '#00ffe7',
            background: '#0a0e1a',
            border: '2px solid #00ffe7',
            borderRadius: 12,
            padding: '12px 32px',
            marginTop: 24,
            marginBottom: 16,
            boxShadow: '0 0 16px #00ffe7',
            cursor: 'pointer',
            letterSpacing: 2,
            textShadow: '0 0 8px #00ffe7',
            transition: 'background 0.2s, color 0.2s',
          }}
          onClick={handleStart}
        >
          Start Simulation
        </button>
      )}
    </div>
  );
}