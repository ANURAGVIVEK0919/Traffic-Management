
import Vehicle from './Vehicle'

// Lane component
export default function Lane({ laneId, vehicles }) {
	// Get base offset for lane
	function getLaneOffset(lane) {
		if (lane === 'north') return { x: -1, z: -4 }
		if (lane === 'south') return { x: 1, z: 4 }
		if (lane === 'east') return { x: 4, z: 1 }
		if (lane === 'west') return { x: -4, z: -1 }
		return { x: 0, z: 0 }
	}

	const offset = getLaneOffset(laneId)

	return (
		<>
			{/* Render each vehicle in lane */}
			{vehicles.map((vehicle, idx) => (
				<Vehicle
					key={vehicle.vehicleId}
					vehicleId={vehicle.vehicleId}
					vehicleType={vehicle.vehicleType}
					position={[offset.x, 0.3, offset.z + idx * 1.2]}
				/>
			))}
		</>
	)
}
