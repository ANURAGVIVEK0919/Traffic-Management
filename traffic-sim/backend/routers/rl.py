
from fastapi import APIRouter, Request
from backend.controllers.rl_controller import handle_rl_decision
from pydantic import BaseModel
from typing import Dict, List

router = APIRouter()
POLICY_MODE = "rl"

class LaneState(BaseModel):
	count: int
	hasAmbulance: bool
	avgWaitTime: float

class RLDecisionRequest(BaseModel):
	lane_counts: List[int] | None = None
	lane_state: Dict[str, LaneState] | None = None
	timestamp: float | None = None
	source: str | None = None
	rl_call_timestamp: float | None = None
	active_green_lane: str | None = None
	line_counts: Dict[str, int] | None = None
	wait_time_by_direction: Dict[str, float] | None = None
	queue_length_by_direction: Dict[str, int] | None = None


def _static_policy_decision(timestamp):
	cycle = int(timestamp // 15) % 4  # 4 lanes
	lane = cycle

	return {
		"action": lane,
		"duration": 15,
		"debug": {
			"policy": "static",
			"session_type": "static",
			"method": "round_robin_time_based"
		}
	}

@router.post("/rl/decision")
def rl_decision(request: RLDecisionRequest, http_request: Request):
	if request is None:
		print('❌ request is None')
		return {'lane': 'north'}

	request_dict = request.dict()
	raw_input_log = request.dict(exclude_none=True)
	lane_counts = request.lane_counts

	if lane_counts is None and request.lane_state:
		lane_counts = [
			request.lane_state['north'].count,
			request.lane_state['south'].count,
			request.lane_state['east'].count,
			request.lane_state['west'].count,
		]

	if isinstance(lane_counts, dict):
		lane_counts = [
			int(lane_counts.get('north', 0) or 0),
			int(lane_counts.get('south', 0) or 0),
			int(lane_counts.get('east', 0) or 0),
			int(lane_counts.get('west', 0) or 0),
		]
	elif isinstance(lane_counts, list):
		lane_counts = [
			int(lane_counts[0] or 0) if len(lane_counts) > 0 else 0,
			int(lane_counts[1] or 0) if len(lane_counts) > 1 else 0,
			int(lane_counts[2] or 0) if len(lane_counts) > 2 else 0,
			int(lane_counts[3] or 0) if len(lane_counts) > 3 else 0,
		]
	else:
		lane_counts = [0, 0, 0, 0]

	source = str(request_dict.get('source') or 'UNKNOWN')
	print("\n===== RL REQUEST =====")
	print("SOURCE:", source)
	print("LANE_COUNTS:", lane_counts)
	print("CLIENT:", http_request.client)
	print("=====================\n")
	print('RAW INPUT TO RL:', raw_input_log)
	print('FINAL lane_counts USED BY RL:', lane_counts)

	timestamp = float(request_dict.get('timestamp') or 0.0)
	if POLICY_MODE == 'static':
		decision = _static_policy_decision(timestamp)
	else:
		state = {'lane_counts': lane_counts}
		decision = handle_rl_decision(state)
	print("RL output:", decision)

	count_map = {
		'north': int(lane_counts[0] if len(lane_counts) > 0 else 0),
		'south': int(lane_counts[1] if len(lane_counts) > 1 else 0),
		'east': int(lane_counts[2] if len(lane_counts) > 2 else 0),
		'west': int(lane_counts[3] if len(lane_counts) > 3 else 0),
	}

	response_lane_state = {}
	for direction in ('north', 'south', 'east', 'west'):
		response_lane_state[direction] = int(count_map.get(direction, 0) or 0)

	decision['lane_state'] = response_lane_state
	debug = decision.setdefault('debug', {})
	debug['lane_metrics'] = {
		'north': {'vehicle_count': int(response_lane_state.get('north', 0))},
		'east': {'vehicle_count': int(response_lane_state.get('east', 0))},
		'south': {'vehicle_count': int(response_lane_state.get('south', 0))},
		'west': {'vehicle_count': int(response_lane_state.get('west', 0))},
	}
	print("RL ACTION:", decision.get('lane'))
	print("RL DURATION:", decision.get('duration'))
	return decision
