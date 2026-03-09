
import { Canvas } from '@react-three/fiber'  // 3D Canvas
import { OrbitControls } from '@react-three/drei'
import Lane from './Lane'
import TrafficLight from './TrafficLight'
import { useSimulationStore } from '../../state/simulationStore'

// Intersection component
export default function Intersection() {
	const lanes = useSimulationStore((state) => state.lanes)
	const lightStates = useSimulationStore((state) => state.lightStates)

	return (
		<Canvas style={{ width: '90vw', height: '90vh', display: 'block' }} camera={{ position: [0, 50, 0], fov: 45 }}>
					   {/* Camera controls */}
					   <OrbitControls enablePan={true} enableZoom={true} enableRotate={true} />
			{/* Lighting */}
			<ambientLight intensity={0.6} />
			<directionalLight position={[0, 40, 0]} intensity={0.9} castShadow />

			   {/* Large ground plane centered at (0,0,0) */}
			   <mesh position={[0, -0.1, 0]}>
				   <boxGeometry args={[70, 0.2, 70]} />
				   <meshStandardMaterial color="#232323" />
			   </mesh>

			   {/* Vertical road centered */}
			   <mesh position={[0, -0.05, 0]}>
				   <boxGeometry args={[10, 0.1, 60]} />
				   <meshStandardMaterial color="#2a2a2a" />
			   </mesh>
			   {/* Horizontal road centered */}
			   <mesh position={[0, -0.05, 0]}>
				   <boxGeometry args={[60, 0.1, 10]} />
				   <meshStandardMaterial color="#2a2a2a" />
			   </mesh>

			   {/* Lane divider lines - vertical */}
			   {[...Array(12)].map((_, i) => (
				   <mesh key={"vline"+i} position={[0, 0.01, -16 + i * 3]}>
					   <boxGeometry args={[0.15, 0.02, 2]} />
					   <meshStandardMaterial color="white" />
				   </mesh>
			   ))}

			   {/* Four traffic lights at stop lines, one per lane */}
			   <>
				   <TrafficLight laneId="north" state={lightStates.north} position={[0, 0.15, -28]} scale={[0.32, 0.32, 0.32]} />
				   <TrafficLight laneId="south" state={lightStates.south} position={[0, 0.15, 28]} scale={[0.32, 0.32, 0.32]} />
				   <TrafficLight laneId="east" state={lightStates.east} position={[28, 0.15, 0]} scale={[0.32, 0.32, 0.32]} />
				   <TrafficLight laneId="west" state={lightStates.west} position={[-28, 0.15, 0]} scale={[0.32, 0.32, 0.32]} />
			   </>

			{/* Zebra crossings - vertical (north & south) */}
			{[...Array(6)].map((_, i) => (
				<mesh key={"zebraN"+i} position={[-1.2 + i * 0.5, 0.02, 6.5]}>
					<boxGeometry args={[0.3, 0.02, 1.2]} />
					<meshStandardMaterial color="white" />
				</mesh>
			))}
			{[...Array(6)].map((_, i) => (
				<mesh key={"zebraS"+i} position={[-1.2 + i * 0.5, 0.02, -6.5]}>
					<boxGeometry args={[0.3, 0.02, 1.2]} />
					<meshStandardMaterial color="white" />
				</mesh>
			))}

			{/* Zebra crossings - horizontal (east & west) */}
			{[...Array(6)].map((_, i) => (
				<mesh key={"zebraE"+i} position={[6.5, 0.02, -1.2 + i * 0.5]}>
					<boxGeometry args={[1.2, 0.02, 0.3]} />
					<meshStandardMaterial color="white" />
				</mesh>
			))}
			{[...Array(6)].map((_, i) => (
				<mesh key={"zebraW"+i} position={[-6.5, 0.02, -1.2 + i * 0.5]}>
					<boxGeometry args={[1.2, 0.02, 0.3]} />
					<meshStandardMaterial color="white" />
				</mesh>
			))}

			   {/* Lanes */}
			   <Lane laneId="north" vehicles={lanes.north} />
			   <Lane laneId="south" vehicles={lanes.south} />
			   <Lane laneId="east" vehicles={lanes.east} />
			   <Lane laneId="west" vehicles={lanes.west} />
		</Canvas>
	)
}
