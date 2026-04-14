
import { create } from 'zustand'  // Zustand import

const initialState = {
	status: 'setup',
	mode: 'simulation',
	timer: null,
	sessionId: null,
	lanes: {
		north: [],
		south: [],
		east: [],
		west: []
	},
	lightStates: {
		north: 'red',
		south: 'red',
		east: 'red',
		west: 'red'
	},
	eventLog: [],
	signalPhases: [],
	totalVehiclesCrossed: 0,
	tickCount: 0,
	timeRemaining: null
}

export const useSimulationStore = create((set) => ({
	...initialState,

	// Set timer and timeRemaining
	setTimer: (timerValue) => set((state) => ({
		timer: timerValue,
		timeRemaining: timerValue
	})),

	// Set sessionId and status
	setSessionId: (sessionId) => set(() => ({
		sessionId,
		status: 'placement'
	})),

	// Set display mode for simulation data source
	setMode: (mode) => set(() => ({
		mode: mode === 'video' ? 'video' : 'simulation'
	})),

	// Set status to running and reset relevant fields
	startSimulation: () => set((state) => ({
		status: 'running',
		tickCount: 0,
		timeRemaining: state.timer
	})),

	// Set status to completed
	freezeSimulation: () => set(() => ({ status: 'completed' })),

	// Update light states
	updateLightStates: (greenLane) => set(() => ({
		lightStates: {
			north: greenLane === 'north' ? 'green' : 'red',
			south: greenLane === 'south' ? 'green' : 'red',
			east: greenLane === 'east' ? 'green' : 'red',
			west: greenLane === 'west' ? 'green' : 'red'
		}
	})),

	// Add vehicle to lane
	addVehicleToLane: (vehicle, laneId) => set((state) => ({
		lanes: {
			...state.lanes,
			[laneId]: [...state.lanes[laneId], vehicle]
		}
	})),

	// Replace lanes with updatedLanes
	updateVehiclePositions: (updatedLanes) => set(() => ({
		lanes: updatedLanes
	})),

	// Append event to eventLog
	logEvent: (event) => set((state) => ({
		eventLog: [...state.eventLog, event]
	})),

	// Append signal phase summary
	addSignalPhase: (phase) => set((state) => ({
		signalPhases: [...state.signalPhases, phase]
	})),

	// Replace signal phases
	setSignalPhases: (signalPhases) => set(() => ({
		signalPhases: Array.isArray(signalPhases) ? signalPhases : []
	})),

	// Increment crossed vehicle count
	incrementTotalVehiclesCrossed: (count = 1) => set((state) => ({
		totalVehiclesCrossed: state.totalVehiclesCrossed + count
	})),

	// Set crossed vehicle count directly
	setTotalVehiclesCrossed: (totalVehiclesCrossed) => set(() => ({
		totalVehiclesCrossed: Number(totalVehiclesCrossed) || 0
	})),

	// Subtract tickInterval from timeRemaining
	decrementTimer: (tickInterval) => set((state) => ({
		timeRemaining: state.timeRemaining !== null ? state.timeRemaining - tickInterval : null
	})),

	// Increment tickCount
	incrementTick: () => set((state) => ({
		tickCount: state.tickCount + 1
	})),

	// Reset store to initial state
	resetStore: () => set(() => ({ ...initialState }))
}))
