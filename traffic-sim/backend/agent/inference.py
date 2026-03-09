import torch
from backend.agent.rl_agent import TrafficRLAgent
import os

# Lane order and durations
LANE_ORDER = ['north', 'east', 'south', 'west']
GREEN_DURATION = 10  # seconds
AMBULANCE_DURATION = 15  # seconds

# Load RL model if available
model = TrafficRLAgent()
model_path = os.path.join('models', 'rl_model.pth')
if os.path.exists(model_path):
	model.load_state_dict(torch.load(model_path, map_location='cpu'))
model.eval()


# Check ambulance priority
def check_ambulance_priority(lane_state):
	ambulance_lanes = [lane['lane_id'] for lane in lane_state if lane.get('has_ambulance')]
	if len(ambulance_lanes) == 1:
		return resolve_single_ambulance(lane_state)
	if len(ambulance_lanes) > 1:
		return resolve_multiple_ambulances(lane_state)
	return None

# Resolve single ambulance
def resolve_single_ambulance(lane_state):
	for lane in lane_state:
		if lane.get('has_ambulance'):
			return {"lane": lane['lane_id'], "duration": AMBULANCE_DURATION}

# Resolve multiple ambulances
def resolve_multiple_ambulances(lane_state):
	max_lane = None
	max_wait = -1
	for lane in lane_state:
		if lane.get('has_ambulance'):
			wait = lane.get('avg_wait_time', 0)
			if wait > max_wait:
				max_wait = wait
				max_lane = lane['lane_id']
	if max_lane:
		return {"lane": max_lane, "duration": AMBULANCE_DURATION}

# Run inference
def run_inference(lane_state):
	# Check ambulance priority first
	priority = check_ambulance_priority(lane_state)
	if priority is not None:
		return priority
	# Build flat input list of 12 values in LANE_ORDER
	features = []
	# Map lane_state to dict for easy lookup
	lane_dict = {lane['lane_id']: lane for lane in lane_state}
	for lane_id in LANE_ORDER:
		lane = lane_dict.get(lane_id, {})
		features.append(lane.get('vehicle_count', 0))
		features.append(1.0 if lane.get('has_ambulance') else 0.0)
		features.append(lane.get('avg_wait_time', 0))
	# Convert to tensor and add batch dimension
	input_tensor = torch.FloatTensor(features).unsqueeze(0)
	# Run model inference
	with torch.no_grad():
		q_values = model(input_tensor)
	# Get lane with highest Q-value
	index = q_values.argmax().item()
	return {"lane": LANE_ORDER[index], "duration": GREEN_DURATION}
