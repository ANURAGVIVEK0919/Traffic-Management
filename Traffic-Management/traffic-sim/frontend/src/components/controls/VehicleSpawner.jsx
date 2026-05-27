
import { useState } from 'react'  // React state
import { useSimulationStore } from '../../state/simulationStore'

// VehicleSpawner component
export default function VehicleSpawner() {
	const [selectedType, setSelectedType] = useState('car')
	const [selectedLane, setSelectedLane] = useState('north')
	const addVehicleToLane = useSimulationStore((state) => state.addVehicleToLane)
	const logEvent = useSimulationStore((state) => state.logEvent)
	const status = useSimulationStore((state) => state.status)
	const timeRemaining = useSimulationStore((state) => state.timeRemaining)
	const timer = useSimulationStore((state) => state.timer)

	// Generate vehicleId
	function generateVehicleId(vehicleType, laneId) {
		const rand = Math.floor(1000 + Math.random() * 9000)
		return `${vehicleType}-${laneId}-${rand}`
	}

	// Validate selection
	function validateSelection(type, lane) {
		if (type && lane) return { valid: true, error: null }
		return { valid: false, error: 'Please select a vehicle type and lane' }
	}

	// Handle add vehicle
	function handleAddVehicle() {
		const { valid, error } = validateSelection(selectedType, selectedLane)
		if (!valid) {
			alert(error)
			return
		}
		const vehicleId = generateVehicleId(selectedType, selectedLane)
		const spawnedAt = timer - timeRemaining
		const vehicle = {
			vehicleId,
			vehicleType: selectedType,
			laneId: selectedLane,
			spawnedAt
		}
		addVehicleToLane(vehicle, selectedLane)
		logEvent({
			eventType: 'vehicle_added',
			vehicleId,
			vehicleType: selectedType,
			laneId: selectedLane,
			timestamp: spawnedAt,
			payload: {}
		})
	}

	return (
		<>
			{/* Vehicle type select */}
			<select value={selectedType} onChange={e => setSelectedType(e.target.value)}>
				<option value="car">car</option>
				<option value="bike">bike</option>
				<option value="ambulance">ambulance</option>
				<option value="truck">truck</option>
				<option value="bus">bus</option>
			</select>
			{/* Lane select */}
			<select value={selectedLane} onChange={e => setSelectedLane(e.target.value)}>
				<option value="north">north</option>
				<option value="south">south</option>
				<option value="east">east</option>
				<option value="west">west</option>
			</select>
			{/* Add Vehicle button */}
			<button onClick={handleAddVehicle}>Add Vehicle</button>
		</>
	)
}
