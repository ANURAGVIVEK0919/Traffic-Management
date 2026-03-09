
from backend.agent.inference import run_inference  # Import inference function

# RL controller function
def handle_rl_decision(request_dict):
	lane_states = request_dict.get('lane_states', [])
	return run_inference(lane_states)
