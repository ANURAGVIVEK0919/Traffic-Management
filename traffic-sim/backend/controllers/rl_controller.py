import time
import os
import random
import csv
from collections import deque

import torch
import torch.nn as nn
import torch.optim as optim

from backend.agent.inference import run_inference  # Import inference function

# =============================================================================
# MODEL LOADING VERIFICATION
# =============================================================================

def _list_model_candidates():
	"""Return candidate model paths from models/ in priority order."""
	if not os.path.exists('models'):
		return []

	files = sorted(os.listdir('models'))
	model_files = [
		f for f in files
		if f.endswith('.pth') or f.endswith('.pt') or f.endswith('.ckpt')
	]

	preferred = []
	if 'dqn_model.pth' in model_files:
		preferred.append('dqn_model.pth')
	if 'final_dqn_model.pth' in model_files:
		preferred.append('final_dqn_model.pth')
	if 'rl_signal_dqn.pth' in model_files:
		preferred.append('rl_signal_dqn.pth')

	preferred.extend([
		f for f in model_files
		if f.endswith('.pth') and f not in ('dqn_model.pth', 'final_dqn_model.pth', 'rl_signal_dqn.pth')
	])
	preferred.extend([f for f in model_files if f.endswith('.pt')])
	preferred.extend([f for f in model_files if f.endswith('.ckpt')])

	return [os.path.join('models', f) for f in preferred]


def _print_available_models():
	"""Print all available model files in models directory."""
	print('[MODEL VERIFICATION] Checking available models...')
	candidates = _list_model_candidates()
	print('MODEL FILES FOUND:')
	for candidate in candidates:
		print(candidate)
	if not candidates:
		print('[MODEL VERIFICATION] No model files found in models/')

_print_available_models()


def _select_model_path():
	candidates = _list_model_candidates()
	selected = candidates[0] if candidates else os.path.join('models', 'final_dqn_model.pth')
	print('SELECTED MODEL:', selected)
	return selected

# Basic state tracking for RL controller
_controller_state = {
	'active_lane': None,
	'last_switch_at': 0.0,
	'ticks_since_last_green': {lane: 0 for lane in ('north', 'south', 'east', 'west')},
}

TRAFFIC_DIRECTIONS = ('north', 'south', 'east', 'west')
ACTIONS = ['north', 'south', 'east', 'west']
MAX_EXPECTED_VEHICLES = 20.0
WAIT_TIME_SCALE = 120.0
QUEUE_SCALE = 20.0
MODEL_PATH = _select_model_path()
INFERENCE_MODE = True  # Force trained-model inference by default
MIN_GREEN_TIME = 8
MAX_GREEN_TIME = 12
FAIRNESS_OVERRIDE_TICKS = 8

# Simple online DQN configuration (4 actions: one per lane)
STATE_SIZE = 14
ACTION_SIZE = 4
REPLAY_CAPACITY = 20000
BATCH_SIZE = 32
MIN_REPLAY_SIZE = 100  # Start training after buffer reaches this size
GAMMA = 0.95
LEARNING_RATE = 1e-3
TRAIN_EVERY_N_STEPS = 1
TARGET_UPDATE_EVERY_N_STEPS = 80
SAVE_EVERY_N_STEPS = 200
EPSILON_START = 1.0
EPSILON_MIN = 0.1
EPSILON_DECAY = 0.995
MODEL_SAVE_PATH = MODEL_PATH
RL_LOG_CSV_PATH = os.path.join('models', 'rl_logs.csv')
ALPHA = 0.3
_ema_state = None
_last_valid_state = None
_state_debug_print_count = 0


def ema_smooth(raw_state):
	global _ema_state
	if raw_state is None:
		return raw_state

	if _ema_state is None:
		_ema_state = raw_state[:]
		return _ema_state[:]

	_ema_state = [
		(ALPHA * new) + ((1 - ALPHA) * old)
		for new, old in zip(raw_state, _ema_state)
	]

	return _ema_state[:]


def stabilize_state(raw_state):
	global _last_valid_state

	if raw_state is None:
		return _last_valid_state

	if _last_valid_state is not None:
		stabilized = []
		for new, old in zip(raw_state, _last_valid_state):
			if new == 0 and old > 0:
				stabilized.append(old)
			else:
				stabilized.append(new)
		_last_valid_state = stabilized
	else:
		_last_valid_state = raw_state[:]

	return _last_valid_state[:]


class SignalDQN(nn.Module):
	def __init__(self, input_size=STATE_SIZE, output_size=ACTION_SIZE):
		super().__init__()
		self.net = nn.Sequential(
			nn.Linear(input_size, 64),
			nn.ReLU(),
			nn.Linear(64, 64),
			nn.ReLU(),
			nn.Linear(64, output_size),
		)

	def forward(self, x):
		return self.net(x)


_q_network = SignalDQN()
_target_network = SignalDQN()
_target_network.load_state_dict(_q_network.state_dict())
_target_network.eval()
_optimizer = optim.Adam(_q_network.parameters(), lr=LEARNING_RATE)
_loss_fn = nn.MSELoss()
_device = torch.device('cpu')
_q_network.to(_device)
_target_network.to(_device)

_replay_buffer = deque(maxlen=REPLAY_CAPACITY)
_epsilon = EPSILON_START
_learn_steps = 0
_last_loss = 0.0
_prev_state = None
_prev_action = None
_prev_reward = None
_last_action = None
_prev_lane_for_reward = None


def reset_rl_state():
	"""Reset all RL controller globals between simulation runs."""
	global _prev_state, _prev_action, _prev_reward, _last_action
	global _prev_lane_for_reward, _ema_state, _last_valid_state
	global _state_debug_print_count, _learn_steps, _last_loss
	global _controller_state

	_prev_state = None
	_prev_action = None
	_prev_reward = None
	_last_action = None
	_prev_lane_for_reward = None
	_ema_state = None
	_last_valid_state = None
	_state_debug_print_count = 0
	_learn_steps = 0
	_last_loss = None

	_controller_state = {
		"active_lane": None,
		"last_switch_at": 0.0,
		"ticks_since_last_green": {lane: 0 for lane in ACTIONS},
	}

	print("[RL RESET] RL controller state reset for new run")


def _save_dqn_model(force=False):
	if not force and _learn_steps % SAVE_EVERY_N_STEPS != 0:
		return
	os.makedirs(os.path.dirname(MODEL_SAVE_PATH), exist_ok=True)
	torch.save(_q_network.state_dict(), MODEL_SAVE_PATH)


def _append_rl_log(timestep, reward, loss, epsilon, action):
	os.makedirs(os.path.dirname(RL_LOG_CSV_PATH), exist_ok=True)
	file_exists = os.path.exists(RL_LOG_CSV_PATH)
	with open(RL_LOG_CSV_PATH, 'a', newline='', encoding='utf-8') as csv_file:
		writer = csv.writer(csv_file)
		if not file_exists:
			writer.writerow(['timestep', 'reward', 'loss', 'epsilon', 'action'])
		writer.writerow([
			int(timestep),
			float(reward),
			float(loss),
			float(epsilon),
			int(action),
		])


def _load_dqn_model_if_exists():
	"""Load saved DQN model if it exists for inference mode."""
	if not os.path.exists(MODEL_PATH):
		print(f"[OK] Model not found at {MODEL_PATH}; starting with fresh model")
		return
	
	try:
		print(f"[MODEL] Attempting to load model from: {MODEL_PATH}")
		state_dict = torch.load(MODEL_PATH, map_location='cpu')
		print(f"MODEL TYPE: {type(state_dict)}")
		print(f"[MODEL] ✓ State dict loaded successfully")
		
		_q_network.load_state_dict(state_dict)
		print(f"[MODEL] ✓ Model weights loaded successfully")
		_q_network.eval()
		global _epsilon
		_epsilon = 0.05
		print(f"[MODEL] Loaded: {MODEL_PATH}")
		print("Using trained RL model")
		
		if INFERENCE_MODE:
			print(f"[MODEL] ✓ Model set to eval mode (inference)")
		else:
			_q_network.train()
			print(f"[MODEL] ✓ Model set to train mode")
		
		print(f"[MODEL] ✓ Model ready for use")
		print('✅ MODEL READY FOR INFERENCE')
		return
		
	except FileNotFoundError as e:
		print(f"[ERROR] Model file not found: {e}")
		return
	except RuntimeError as e:
		print(f"[ERROR] Model loading failed (architecture mismatch?): {e}")
		return
	except Exception as e:
		print(f"[ERROR] Unexpected error loading model: {e}")
		print('❌ MODEL STILL NOT LOADED')
		return


def _choose_action_epsilon_greedy(state_norm):
	global _epsilon
	if random.random() < _epsilon:
		action = random.randint(0, ACTION_SIZE - 1)
	else:
		state_tensor = torch.tensor(state_norm, dtype=torch.float32).unsqueeze(0)
		with torch.no_grad():
			q_values = _q_network(state_tensor)
		action = int(torch.argmax(q_values, dim=1).item())

# Apply epsilon decay regardless of mode - necessary for training convergence
		_epsilon = max(0.05, _epsilon * 0.995)
	return action


def _train_step_if_ready():
	global _last_loss
	if len(_replay_buffer) < BATCH_SIZE:
		return
	if _learn_steps % TRAIN_EVERY_N_STEPS != 0:
		return

	batch = random.sample(_replay_buffer, BATCH_SIZE)
	states = torch.tensor([item[0] for item in batch], dtype=torch.float32)
	actions = torch.tensor([item[1] for item in batch], dtype=torch.int64).unsqueeze(1)
	rewards = torch.tensor([item[2] for item in batch], dtype=torch.float32)
	next_states = torch.tensor([item[3] for item in batch], dtype=torch.float32)

	q_values = _q_network(states).gather(1, actions).squeeze(1)
	with torch.no_grad():
		next_q_values = _target_network(next_states).max(dim=1)[0]
		target_q = rewards + (GAMMA * next_q_values)

	loss = _loss_fn(q_values, target_q)
	_optimizer.zero_grad()
	loss.backward()
	_optimizer.step()
	_last_loss = float(loss.item())

	if _learn_steps % TARGET_UPDATE_EVERY_N_STEPS == 0:
		_target_network.load_state_dict(_q_network.state_dict())

	_save_dqn_model()


_load_dqn_model_if_exists()

print("[INIT] ========== RL CONTROLLER INITIALIZED ==========")
print(f"[INIT] MODEL_PATH: {MODEL_PATH}")
print(f"[INIT] INFERENCE_MODE: {INFERENCE_MODE}")
print(f"[INIT] Model training: {_q_network.training}")
print(f"[INIT] Epsilon: {_epsilon}")
print("[INIT] ================================================")


def _normalize_directional(source, default=0.0):
	normalized = {}
	for direction in TRAFFIC_DIRECTIONS:
		value = source.get(direction, default) if isinstance(source, dict) else default
		normalized[direction] = float(value)
	return normalized


def _build_state_vector(request_dict):
	counts = _normalize_directional(request_dict.get('line_counts') or {}, default=0.0)
	waits = _normalize_directional(request_dict.get('wait_time_by_direction') or {}, default=0.0)
	queues = _normalize_directional(request_dict.get('queue_length_by_direction') or {}, default=0.0)
	queues_scaled = {direction: float(value) * 2.0 for direction, value in queues.items()}
	diff_ns = (waits['north'] - waits['south']) / 100.0
	diff_ew = (waits['east'] - waits['west']) / 100.0
	state_dict = {
		'line_counts': counts,
		'wait_time_by_direction': waits,
		'queue_length_by_direction': queues,
		'queue_length_by_direction_scaled': queues_scaled,
		'diff_ns': diff_ns,
		'diff_ew': diff_ew,
	}

	state_raw = [
		counts['north'], counts['south'], counts['east'], counts['west'],
		waits['north'], waits['south'], waits['east'], waits['west'],
		queues_scaled['north'], queues_scaled['south'], queues_scaled['east'], queues_scaled['west'],
		diff_ns, diff_ew,
	]

	state_norm = [
		counts['north'] / MAX_EXPECTED_VEHICLES,
		counts['south'] / MAX_EXPECTED_VEHICLES,
		counts['east'] / MAX_EXPECTED_VEHICLES,
		counts['west'] / MAX_EXPECTED_VEHICLES,
		waits['north'] / WAIT_TIME_SCALE,
		waits['south'] / WAIT_TIME_SCALE,
		waits['east'] / WAIT_TIME_SCALE,
		waits['west'] / WAIT_TIME_SCALE,
		queues_scaled['north'] / QUEUE_SCALE,
		queues_scaled['south'] / QUEUE_SCALE,
		queues_scaled['east'] / QUEUE_SCALE,
		queues_scaled['west'] / QUEUE_SCALE,
		diff_ns,
		diff_ew,
	]

	return counts, waits, queues, queues_scaled, state_raw, state_norm


def _select_action_from_state(counts, waits, queues):
	ns_pressure = (counts['north'] + counts['south']) + (waits['north'] + waits['south']) + (queues['north'] + queues['south'])
	ew_pressure = (counts['east'] + counts['west']) + (waits['east'] + waits['west']) + (queues['east'] + queues['west'])
	# Action 0: NS green, Action 1: EW green
	return 0 if ns_pressure >= ew_pressure else 1


def _compute_reward(waits, queues, action, request_dict=None):
	global _prev_lane_for_reward
	wait_time_by_direction = waits if isinstance(waits, dict) else {}
	queue_length_by_direction = queues if isinstance(queues, dict) else {}

	total_wait = float(sum(wait_time_by_direction.values()))
	total_queue = float(sum(queue_length_by_direction.values()))

	if isinstance(wait_time_by_direction, dict) and wait_time_by_direction:
		max_wait_lane = max(wait_time_by_direction, key=wait_time_by_direction.get)
	else:
		max_wait_lane = ACTIONS[0]

	chosen_lane = ACTIONS[action] if 0 <= int(action) < len(ACTIONS) else ACTIONS[0]

	# Softer shaping improves learning stability.
	reward = - (0.5 * total_wait + 0.2 * total_queue)

	if chosen_lane == max_wait_lane:
		reward += 3
	else:
		reward -= 1

	if _prev_lane_for_reward is not None and chosen_lane != _prev_lane_for_reward:
		reward -= min(2.0, 0.1 * total_wait)

	_prev_lane_for_reward = chosen_lane

	print(f"[REWARD] wait={total_wait:.2f}, queue={total_queue}, chosen={chosen_lane}, best={max_wait_lane}, reward={reward:.2f}")

	return reward


def _safe_loss_value():
	return float(_last_loss) if _last_loss is not None else 0.0


def _choose_best_non_empty_lane(counts, waits, queues=None):
	queues = queues if isinstance(queues, dict) else {}
	non_empty = [lane for lane in ACTIONS if float(counts.get(lane, 0) or 0) > 0]
	if not non_empty:
		return None
	return max(
		non_empty,
		key=lambda lane: (
			float(counts.get(lane, 0) or 0),
			float(waits.get(lane, 0) or 0),
			float(queues.get(lane, 0) or 0),
		)
	)


def _apply_tick_update(served_lane):
	ticks = _controller_state.setdefault('ticks_since_last_green', {lane: 0 for lane in ACTIONS})
	for lane in ACTIONS:
		if lane == served_lane:
			ticks[lane] = 0
		else:
			ticks[lane] = int(ticks.get(lane, 0)) + 1
	return dict(ticks)


def _normalize_lane_counts(lane_counts):
	if isinstance(lane_counts, dict):
		return {
			'north': int(lane_counts.get('north', 0) or 0),
			'south': int(lane_counts.get('south', 0) or 0),
			'east': int(lane_counts.get('east', 0) or 0),
			'west': int(lane_counts.get('west', 0) or 0),
		}
	if isinstance(lane_counts, (list, tuple)) and len(lane_counts) >= 4:
		return {
			'north': int(lane_counts[0] or 0),
			'south': int(lane_counts[1] or 0),
			'east': int(lane_counts[2] or 0),
			'west': int(lane_counts[3] or 0),
		}
	return None


def _lane_counts_to_lane_state(counts):
	return {
		lane: {
			'count': int(counts.get(lane, 0) or 0),
			'hasAmbulance': False,
			'avgWaitTime': 0.0,
		}
		for lane in ACTIONS
	}


def handle_rl_decision(request_dict):
	"""Simple RL decision handler - no MIN_GREEN override."""
	from backend.routers.rl import POLICY_MODE
	print(f"[RL DECISION] POLICY_MODE={POLICY_MODE}")

	request_dict = request_dict if isinstance(request_dict, dict) else {}
	global _learn_steps, _prev_state, _prev_action, _prev_reward, _state_debug_print_count
	default_lane_state = {
		'north': {'count': 0, 'hasAmbulance': False, 'avgWaitTime': 0.0},
		'south': {'count': 0, 'hasAmbulance': False, 'avgWaitTime': 0.0},
		'east': {'count': 0, 'hasAmbulance': False, 'avgWaitTime': 0.0},
		'west': {'count': 0, 'hasAmbulance': False, 'avgWaitTime': 0.0},
	}
	if request_dict is None:
		print('❌ request is None')
		return {'lane': 'north', 'lane_state': default_lane_state, 'debug': {}}

	ambulance = request_dict.get('ambulance') if isinstance(request_dict, dict) else None
	if isinstance(ambulance, dict):
		for lane in TRAFFIC_DIRECTIONS:
			if bool(ambulance.get(lane, False)):
				print(f"[OVERRIDE] Ambulance detected in {lane} -> priority given")
				return {
					'lane': lane,
					'duration': 10,
					'debug': {
						'override': 'ambulance_priority',
						'lane': lane,
					},
				}

	lane_counts = _normalize_lane_counts(request_dict.get('lane_counts'))
	if lane_counts is not None:
		print("[RL INPUT] lane_counts:", lane_counts)
		if sum(lane_counts.values()) == 0:
			return {
				'lane': 'north',
				'duration': 10,
				'debug': {'reason': 'no_vehicles'}
			}

		lane_state = _lane_counts_to_lane_state(lane_counts)
		decision = run_inference(lane_state)
		if not isinstance(decision, dict):
			print('⚠️ Invalid RL decision output:', decision)
			decision = {'lane': 'north', 'duration': 10, 'debug': {}}

		selected_lane = decision.get('lane')
		if selected_lane not in ACTIONS:
			print('⚠️ Invalid lane:', selected_lane)
			selected_lane = 'north'
			decision['lane'] = selected_lane

		best_non_empty_lane = _choose_best_non_empty_lane(lane_counts, {lane: 0.0 for lane in ACTIONS}, {})
		if best_non_empty_lane is not None and int(lane_counts.get(selected_lane, 0) or 0) <= 0:
			print(f"[OVERRIDE] Inference selected empty lane ({selected_lane}); switching to {best_non_empty_lane}")
			selected_lane = best_non_empty_lane
			decision['lane'] = selected_lane

		decision['duration'] = int(decision.get('duration') or 10)
		debug = decision.setdefault('debug', {})
		debug['source'] = 'lane_counts'
		debug['counts'] = lane_counts
		debug['state'] = [lane_counts[lane] for lane in ACTIONS]
		debug['normalized_state'] = [round(float(lane_counts[lane]) / MAX_EXPECTED_VEHICLES, 4) for lane in ACTIONS]
		return decision

	print('MODE:', 'INFERENCE' if INFERENCE_MODE else 'TRAINING')
	lane_state = request_dict.get('lane_state') or default_lane_state
	if not isinstance(lane_state, dict):
		print(f"[RL STATE WARNING][rl_controller] lane_state must be a dict, got {type(lane_state).__name__}")
		lane_state = default_lane_state

	# Initialize directional metrics from lane_state so downstream logic always has values.
	counts = {
		direction: float(((lane_state.get(direction) if isinstance(lane_state.get(direction), dict) else {}).get('count', 0) or 0))
		for direction in ACTIONS
	}
	waits = {
		direction: float(((lane_state.get(direction) if isinstance(lane_state.get(direction), dict) else {}).get('avgWaitTime', 0.0) or 0.0))
		for direction in ACTIONS
	}
	queues = {direction: float(counts.get(direction, 0) or 0) for direction in ACTIONS}

	for lane, data in lane_state.items():
		if not isinstance(data, dict):
			continue
		if bool(data.get('hasAmbulance', False)):
			print(f"[OVERRIDE] Ambulance detected in lane_state for {lane}")
			return {
				'lane': lane,
				'duration': 5,
				'debug': {'reason': 'ambulance_override'}
			}

	metrics_available = all(
		isinstance(request_dict.get(key), dict)
		for key in ('line_counts', 'wait_time_by_direction', 'queue_length_by_direction')
	)

	# If full directional metrics are missing, derive them from lane_state so RL can still run.
	if not metrics_available and isinstance(lane_state, dict):
		derived_counts = {}
		derived_waits = {}
		derived_queues = {}
		for direction in TRAFFIC_DIRECTIONS:
			lane_info = lane_state.get(direction) if isinstance(lane_state.get(direction), dict) else {}
			count_value = float(lane_info.get('count', 0) or 0)
			wait_value = float(lane_info.get('avgWaitTime', 0.0) or 0.0)
			derived_counts[direction] = count_value
			derived_waits[direction] = wait_value
			# Queue length fallback: use count when explicit queue is unavailable.
			derived_queues[direction] = count_value
		request_dict['line_counts'] = derived_counts
		request_dict['wait_time_by_direction'] = derived_waits
		request_dict['queue_length_by_direction'] = derived_queues
		metrics_available = True

	if metrics_available:
		counts, waits, queues, queues_scaled, state_raw, state_norm = _build_state_vector(request_dict)
		print("[DEBUG] line_counts:", counts)
		print("[DEBUG] waits:", waits)
		print("[DEBUG] queues:", queues)

		# Avoid dead decisions when no traffic is present.
		if sum(counts.values()) == 0:
			return {
				"lane": random.choice(ACTIONS),
				"duration": 5,
				"debug": {"reason": "no_vehicles"}
			}

		raw_state = [float(v) for v in state_norm]
		stable = stabilize_state(raw_state)
		state = ema_smooth(stable)
		if state is None:
			state = raw_state[:]
		state_norm = [float(v) for v in state]

		if _state_debug_print_count < 20:
			print("RAW STATE:", raw_state)
			print("STABLE STATE:", state)
			_state_debug_print_count += 1

		print('DEBUG request:', request_dict)
		print("STATE:", state_raw)
		print(f"[RL STATE] counts={[round(x,2) for x in state[:4]]} "
			  f"waits={[round(x,2) for x in state[4:8]]} "
			  f"queues={[round(x,2) for x in state[8:12]]} "
			  f"diffs={[round(x,2) for x in state[12:14]]}")

		# Replay tuple: (state, action, reward, next_state)
		# Store experience UNCONDITIONALLY - always collect transitions for training
		if _prev_state is not None and _prev_action is not None and _prev_reward is not None:
			next_state = state_norm if state_norm is not None else _prev_state
			_replay_buffer.append((_prev_state, _prev_action, float(_prev_reward), next_state))
			print(f"[BUFFER] stored transition, size now {len(_replay_buffer)}")

		# TRAINING LOGIC - runs UNCONDITIONALLY regardless of mode
		if len(_replay_buffer) >= MIN_REPLAY_SIZE:
			_train_step_if_ready()

		if INFERENCE_MODE:
			# Use trained DQN model for inference action selection.
			_q_network.eval()
			state_tensor = torch.tensor(state_norm, dtype=torch.float32).unsqueeze(0)
			with torch.no_grad():
				q_values = _q_network(state_tensor)
			action = int(torch.argmax(q_values, dim=1).item())
			print(f"[INFERENCE] DQN selected action={action} lane={ACTIONS[action]}")
		else:
			if _learn_steps < 3000:
				action = random.randint(0, ACTION_SIZE - 1)
			else:
				action = _choose_action_epsilon_greedy(state_norm)

		reward = _compute_reward(waits, queues, action, request_dict)
		print("ACTION:", action)
		print("REWARD:", reward)
		print("EPSILON:", _epsilon)
		print(f"[TRAINING CHECK] buffer={len(_replay_buffer)}, min_required={MIN_REPLAY_SIZE}")
		print("LOSS:", round(_safe_loss_value(), 6))
		_learn_steps += 1

		_prev_state = list(state_norm)
		_prev_action = int(action)
		_prev_reward = float(reward)

		_append_rl_log(
			timestep=_learn_steps,
			reward=float(reward),
			loss=_safe_loss_value(),
			epsilon=float(_epsilon),
			action=int(action),
		)

		selected_lane = ACTIONS[action]
		non_empty_lanes = [lane for lane in ACTIONS if counts.get(lane, 0) > 0]

		# If selected lane is empty, switch immediately to the best non-empty lane.
		if counts.get(selected_lane, 0) == 0:
			if non_empty_lanes:
				selected_lane = max(
					non_empty_lanes,
					key=lambda l: counts[l] + waits[l]
				)
				print(f"[FIX] Empty lane avoided -> switched to {selected_lane}")
			else:
				return {
					"lane": random.choice(ACTIONS),
					"duration": 5,
					"debug": {"reason": "all_empty"}
				}
			action = ACTIONS.index(selected_lane)
		decision = {
			'lane': selected_lane,
			'duration': 10,
			'debug': {
				'strategy': 'online_dqn',
				'action': action,
				'action_meaning': selected_lane,
				'reward': round(float(reward), 4),
				'state': state_raw,
				'normalized_state': [round(float(v), 4) for v in state_norm],
				'epsilon': round(float(_epsilon), 6),
				'replay_size': int(len(_replay_buffer)),
				'train_step': int(_learn_steps),
				'loss': round(_safe_loss_value(), 6),
				'counts': counts,
				'wait_time_by_direction': waits,
				'queue_length_by_direction': queues,
				'queue_length_by_direction_scaled': queues_scaled,
			},
		}
		print(
			f"[RL] state={state_raw} action={action} lane={selected_lane} "
			f"reward={round(float(reward), 4)} eps={round(float(_epsilon), 4)} "
			f"replay={len(_replay_buffer)} loss={round(_safe_loss_value(), 6)}"
		)
	else:
		decision = run_inference(lane_state)
		if not isinstance(decision, dict):
			print('⚠️ Invalid RL decision output:', decision)
			decision = {'lane': 'north', 'debug': {}}
		selected_lane = decision.get('lane')
		if selected_lane not in ACTIONS:
			print('⚠️ Invalid lane:', selected_lane)
			selected_lane = 'north'
			decision['lane'] = selected_lane
		fallback_counts = {
			lane: int(((lane_state.get(lane) if isinstance(lane_state.get(lane), dict) else {}).get('count', 0) or 0))
			for lane in ACTIONS
		}
		fallback_waits = {
			lane: float(((lane_state.get(lane) if isinstance(lane_state.get(lane), dict) else {}).get('avgWaitTime', 0.0) or 0.0))
			for lane in ACTIONS
		}
		best_non_empty_lane = _choose_best_non_empty_lane(fallback_counts, fallback_waits, {})
		if best_non_empty_lane is not None and float(fallback_counts.get(selected_lane, 0) or 0) <= 0:
			print(f"[OVERRIDE] Inference selected empty lane ({selected_lane}); switching to {best_non_empty_lane}")
			selected_lane = best_non_empty_lane
			decision['lane'] = selected_lane
		debug = decision.setdefault('debug', {})
		if selected_lane in ACTIONS:
			default_action = ACTIONS.index(selected_lane)
		else:
			default_action = 0
		debug.setdefault('action', default_action)
		debug.setdefault('action_meaning', ACTIONS[debug['action']])
		debug.setdefault('state', [])
		debug.setdefault('normalized_state', [])
		debug.setdefault('reward', 0.0)
	now = float(request_dict.get('timestamp') or time.monotonic())

	current_lane = _controller_state['active_lane']
	time_since_last_switch = now - _controller_state['last_switch_at']
	ticks_since_last_green = _controller_state.setdefault('ticks_since_last_green', {lane: 0 for lane in ACTIONS})
	print("Ticks since last green:", ticks_since_last_green)
	ticks_vector = [int(ticks_since_last_green.get(lane, 0)) for lane in ACTIONS]
	max_ticks = max(ticks_vector)
	lane_with_max_wait = int(ticks_vector.index(max_ticks))
	fairness_override = max_ticks > FAIRNESS_OVERRIDE_TICKS

	if fairness_override:
		action = lane_with_max_wait
		print("FAIRNESS TRIGGERED:", lane_with_max_wait)
		print("Ticks:", ticks_since_last_green)
		print("FAIRNESS OVERRIDE APPLIED:", action)
		selected_lane = ACTIONS[action]
		for i, lane in enumerate(ACTIONS):
			if i == action:
				ticks_since_last_green[lane] = 0
			else:
				ticks_since_last_green[lane] = int(ticks_since_last_green.get(lane, 0)) + 1
		decision['lane'] = selected_lane
		_controller_state['active_lane'] = selected_lane
		_controller_state['last_switch_at'] = now
		updated_ticks = dict(ticks_since_last_green)
		debug = decision.setdefault('debug', {})
		debug['fairness_override'] = True
		debug['fairness_override_threshold'] = FAIRNESS_OVERRIDE_TICKS
		debug['fairness_override_action'] = action
		debug['ticks_since_last_green'] = updated_ticks
		return decision

	STICKINESS_BONUS = 2.5

	# Encourage staying on current lane when it still has pressure to clear smoothly.
	if current_lane and counts.get(current_lane, 0) > 0:
		current_score = counts[current_lane] + waits[current_lane] + STICKINESS_BONUS
		new_score = counts[selected_lane] + waits[selected_lane]

		if current_score >= new_score:
			print(f"[STAY] Staying on {current_lane} (better to clear queue)")
			selected_lane = current_lane
			decision['lane'] = selected_lane

	# If no lane yet, initialize.
	if current_lane is None:
		_controller_state['active_lane'] = selected_lane
		_controller_state['last_switch_at'] = now
		updated_ticks = _apply_tick_update(selected_lane)
		decision['lane'] = selected_lane
		debug = decision.setdefault('debug', {})
		debug['fairness_override'] = False
		debug['fairness_override_threshold'] = FAIRNESS_OVERRIDE_TICKS
		debug['ticks_since_last_green'] = updated_ticks
		return decision

	# Force switch window to avoid starvation.
	if time_since_last_switch > MAX_GREEN_TIME:
		print("[FORCE SWITCH - fairness]")
		selected_lane = max(waits, key=waits.get)
		_controller_state['active_lane'] = selected_lane
		_controller_state['last_switch_at'] = now
		updated_ticks = _apply_tick_update(selected_lane)
		decision['lane'] = selected_lane
		debug = decision.setdefault('debug', {})
		debug['fairness_override'] = False
		debug['fairness_override_threshold'] = FAIRNESS_OVERRIDE_TICKS
		debug['ticks_since_last_green'] = updated_ticks
		return decision

	# Prevent rapid switching before minimum green time.
	if selected_lane != current_lane and time_since_last_switch < MIN_GREEN_TIME:
		print(f"[LOCK] Holding {current_lane} ({time_since_last_switch:.2f}s < {MIN_GREEN_TIME}s)")
		updated_ticks = _apply_tick_update(current_lane)
		decision['lane'] = current_lane
		debug = decision.setdefault('debug', {})
		debug['fairness_override'] = False
		debug['fairness_override_threshold'] = FAIRNESS_OVERRIDE_TICKS
		debug['ticks_since_last_green'] = updated_ticks
		return decision

	_controller_state['active_lane'] = selected_lane
	_controller_state['last_switch_at'] = now
	updated_ticks = _apply_tick_update(selected_lane)
	decision['lane'] = selected_lane
	print("Selected action:", ACTIONS.index(selected_lane) if selected_lane in ACTIONS else -1)

	debug = decision.setdefault('debug', {})
	debug['min_green_remaining'] = 0.0
	debug['switch_locked'] = False
	debug['fairness_override'] = False
	debug['fairness_override_threshold'] = FAIRNESS_OVERRIDE_TICKS
	debug['ticks_since_last_green'] = updated_ticks

	return decision
