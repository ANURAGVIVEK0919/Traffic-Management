import json
import os
import random
import numpy as np
import torch

# Lane order and durations
LANE_ORDER = ['north', 'east', 'south', 'west']
GREEN_DURATION = 10  # seconds
COUNT_NORMALIZATION_SCALE = 10.0
WAIT_NORMALIZATION_SCALE = 30.0

# LSTM model path
LSTM_MODEL_PATH = os.path.join('models', 'rl_model.pth')

class RLAgent:
    """Simple tabular Q-learning agent with epsilon-greedy action selection."""

    def __init__(
        self,
        qtable_path='models/q_table.json',
        alpha=0.1,
        gamma=0.9,
        epsilon=0.1,
        epsilon_decay=0.995,
        min_epsilon=0.01,
    ):
        self.actions = list(LANE_ORDER)
        self.alpha = float(alpha)
        self.gamma = float(gamma)
        self.epsilon = float(epsilon)
        self.epsilon_decay = float(epsilon_decay)
        self.min_epsilon = float(min_epsilon)
        self.qtable_path = qtable_path
        self.q_table = {}
        self.last_state_key = None
        self.last_action = None
        self.update_count = 0
        self.decision_count = 0
        self._load_q_table()

    def _count_bucket(self, count_value):
        count_value = float(count_value or 0)
        if count_value <= 3:
            return 0
        if count_value <= 7:
            return 1
        return 2

    def _wait_bucket(self, wait_value):
        wait_value = float(wait_value or 0)
        if wait_value <= 5:
            return 0
        if wait_value <= 15:
            return 1
        return 2

    def encode_state(self, lane_dict):
        # State tuple: (count_n, wait_n, count_e, wait_e, count_s, wait_s, count_w, wait_w)
        encoded = []
        for lane_id in LANE_ORDER:
            lane = lane_dict.get(lane_id, {})
            encoded.append(self._count_bucket(lane.get('vehicle_count', 0)))
            encoded.append(self._wait_bucket(lane.get('avg_wait_time', 0.0)))
        return tuple(encoded)

    def _state_key(self, state_tuple):
        return ','.join(str(value) for value in state_tuple)

    def _ensure_state(self, state_key):
        if state_key not in self.q_table:
            self.q_table[state_key] = {action: 0.0 for action in self.actions}

    def get_q_values(self, state_tuple):
        state_key = self._state_key(state_tuple)
        self._ensure_state(state_key)
        return state_key, self.q_table[state_key]

    def has_state(self, state_tuple):
        return self._state_key(state_tuple) in self.q_table

    def choose_action(self, state_tuple):
        state_key, q_values = self.get_q_values(state_tuple)
        explore = random.random() < self.epsilon
        if explore:
            action = random.choice(self.actions)
        else:
            action = max(self.actions, key=lambda lane: q_values.get(lane, 0.0))
        return state_key, action, q_values, explore

    def compute_reward(self, lane_dict):
        """Compute reward: minimize total wait time, priority for ambulances."""
        total_wait = 0.0
        ambulance_penalty = 0.0
        for lane_id in LANE_ORDER:
            lane = lane_dict.get(lane_id, {})
            wait_time = float(lane.get('avg_wait_time', 0.0) or 0.0)
            total_wait += wait_time
            if lane.get('has_ambulance'):
                ambulance_penalty += wait_time * 2.0
        return -(total_wait + ambulance_penalty)

    def update_q(self, prev_state_key, action, reward, next_state_key):
        self._ensure_state(prev_state_key)
        self._ensure_state(next_state_key)
        current_q = float(self.q_table[prev_state_key].get(action, 0.0))
        next_max_q = max(float(value) for value in self.q_table[next_state_key].values())
        updated_q = current_q + self.alpha * (float(reward) + self.gamma * next_max_q - current_q)
        self.q_table[prev_state_key][action] = float(updated_q)
        self.update_count += 1
        if self.update_count % 25 == 0:
            self._save_q_table()

    def observe_transition(self, prev_state_key, action, reward, next_state_key):
        if prev_state_key is None or action is None:
            return
        self.update_q(prev_state_key, action, reward, next_state_key)

    def commit_action(self, state_key, action):
        self.last_state_key = state_key
        self.last_action = action
        self.decision_count += 1
        self.epsilon = max(self.min_epsilon, self.epsilon * self.epsilon_decay)

    def table_size(self):
        return len(self.q_table)

    def _load_q_table(self):
        if not os.path.exists(self.qtable_path):
            return
        try:
            with open(self.qtable_path, 'r', encoding='utf-8') as infile:
                data = json.load(infile)
            if isinstance(data, dict):
                self.q_table = {
                    str(state_key): {
                        str(action): float(value)
                        for action, value in action_values.items()
                    }
                    for state_key, action_values in data.items()
                    if isinstance(action_values, dict)
                }
        except Exception:
            # Keep defaults if persisted data is unreadable.
            self.q_table = {}

    def _save_q_table(self):
        os.makedirs(os.path.dirname(self.qtable_path), exist_ok=True)
        with open(self.qtable_path, 'w', encoding='utf-8') as outfile:
            json.dump(self.q_table, outfile)


def resolve_lane_value(lane, raw_key, normalized_key, scale, default=0.0):
    normalized_value = lane.get(normalized_key)
    if normalized_value is not None:
        normalized_value = max(0.0, min(1.0, float(normalized_value)))
        return normalized_value * float(scale)
    return float(lane.get(raw_key, default) or default)


def prepare_lane_dict(lane_dict):
    prepared = {}
    for lane_id in LANE_ORDER:
        lane = lane_dict.get(lane_id, {})
        prepared[lane_id] = {
            'vehicle_count': resolve_lane_value(lane, 'vehicle_count', 'normalized_vehicle_count', COUNT_NORMALIZATION_SCALE, 0.0),
            'avg_wait_time': resolve_lane_value(lane, 'avg_wait_time', 'normalized_avg_wait_time', WAIT_NORMALIZATION_SCALE, 0.0),
            'has_ambulance': bool(lane.get('has_ambulance', False)),
        }
    return prepared


agent = RLAgent()


def build_lane_metrics(lane_dict):
    lane_dict = prepare_lane_dict(lane_dict)
    metrics = {}
    for lane_id in LANE_ORDER:
        lane = lane_dict.get(lane_id, {})
        metrics[lane_id] = {
            "vehicle_count": lane.get('vehicle_count', 0),
            "avg_wait_time": lane.get('avg_wait_time', 0),
            "has_ambulance": lane.get('has_ambulance', False)
        }
    return metrics


def run_inference(lane_state):
    """Simple RL inference using Q-table with epsilon-greedy action selection."""
    # Map lane_state to dict for easy lookup.
    lane_dict = {lane['lane_id']: lane for lane in lane_state}
    lane_dict = prepare_lane_dict(lane_dict)
    state_tuple = agent.encode_state(lane_dict)
    reward = agent.compute_reward(lane_dict)

    # Simple Q-table action selection (epsilon-greedy already built in)
    state_key, selected_lane, q_values, explore = agent.choose_action(state_tuple)
    
    raw_scores = {
        lane_id: round(float(q_values.get(lane_id, 0.0)), 4)
        for lane_id in LANE_ORDER
    }
    selected_q_value = float(q_values.get(selected_lane, 0.0))

    # Update Q-table from previous transition
    agent.observe_transition(agent.last_state_key, agent.last_action, reward, state_key)
    agent.commit_action(state_key, selected_lane)

    # Simple logging
    decision_reason = f'RL {'exploration' if explore else 'exploitation'}'
    print(f"RL BASIC ACTION: {selected_lane} | Q-VALUE: {round(selected_q_value, 4)} | EPSILON: {round(agent.epsilon, 4)} | EXPLORE: {explore}")

    return {
        "lane": selected_lane,
        "duration": GREEN_DURATION,
        "debug": {
            "strategy": "rl_basic",
            "source": "Q-table",
            "decision_reason": decision_reason,
            "selected_lane_score": raw_scores[selected_lane],
            "lane_scores": raw_scores,
            "masked_out_lanes": [],
            "lane_metrics": build_lane_metrics(lane_dict),
            "reward": round(float(reward), 4),
            "state": list(state_tuple),
            "q_value": round(float(selected_q_value), 4),
            "epsilon": round(float(agent.epsilon), 4),
        }
    }
