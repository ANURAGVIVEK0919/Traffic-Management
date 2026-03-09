import { useGLTF } from '@react-three/drei'

// Model path mapping
const VEHICLE_MODELS = {
  car: '/models/sedan.glb',
  bike: '/models/race.glb',
  ambulance: '/models/ambulance.glb',
  truck: '/models/truck.glb',
  bus: '/models/delivery.glb'
}

// Scale mapping
const VEHICLE_SCALES = {
  car: [0.4, 0.4, 0.4],
  bike: [0.3, 0.3, 0.3],
  ambulance: [0.45, 0.45, 0.45],
  truck: [0.5, 0.5, 0.5],
  bus: [0.5, 0.5, 0.5]
}

// Vehicle model component using GLB
export default function VehicleModel({ vehicleType, position, laneId }) {
  const modelPath = VEHICLE_MODELS[vehicleType] || VEHICLE_MODELS.car
  const scale = VEHICLE_SCALES[vehicleType] || [0.4, 0.4, 0.4]

  // Load and clone GLB model
  const { scene } = useGLTF(modelPath)
  const clonedScene = scene.clone()

  // Rotate to face intersection based on lane
  let rotationY = 0
  if (laneId === 'north') rotationY = Math.PI
  else if (laneId === 'south') rotationY = 0
  else if (laneId === 'east') rotationY = Math.PI / 2
  else if (laneId === 'west') rotationY = -Math.PI / 2

    // Slightly lift vehicle above road to avoid clipping
    const liftedPosition = [position[0], position[1] + 0.2, position[2]]
    return (
      <primitive
        object={clonedScene}
        position={liftedPosition}
        scale={scale}
        rotation={[0, rotationY, 0]}
      />
    )
}

// Preload all models for performance
Object.values(VEHICLE_MODELS).forEach(path => useGLTF.preload(path))