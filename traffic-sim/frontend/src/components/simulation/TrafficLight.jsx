
import { useRef } from 'react'
import { useGLTF } from '@react-three/drei'

// Preload traffic light model once when app starts
useGLTF.preload('/models/traffic_light.glb')

// TrafficLight component
export default function TrafficLight({ laneId, state, position, scale }) {
	// Load GLB model
	const { scene } = useGLTF('/models/traffic_light.glb')
	const clonedScene = scene.clone()

	// Rotation logic based on laneId
	let rotationY = 0
	if (laneId === 'north') rotationY = 0
	else if (laneId === 'south') rotationY = Math.PI
	else if (laneId === 'east') rotationY = -Math.PI / 2
	else if (laneId === 'west') rotationY = Math.PI / 2

	return (
		<primitive
			object={clonedScene}
			position={position}
			scale={scale}
			rotation={[0, rotationY, 0]}
		/>
	)
}
