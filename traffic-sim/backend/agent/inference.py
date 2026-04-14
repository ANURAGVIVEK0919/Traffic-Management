import json
import os
import numpy as np
import torch
import torch.nn as nn
from backend.agent.rl_agent import TrafficRLAgent

# Lane order and durations
LANE_ORDER = ['north', 'east', 'south', 'west']
GREEN_DURATION = 10  # seconds

# DQN model path
MODEL_PATH = "models/final_dqn_model.pth"
MODEL_EPSILON = 0.05


class SequentialDQN(nn.Module):
    """Compatibility loader for checkpoints saved from Sequential(net.*) architecture."""

    def __init__(self, input_size=14, output_size=4):
        super().__init__()
        self.input_size = int(input_size)
        self.net = nn.Sequential(
            nn.Linear(self.input_size, 64),
            nn.ReLU(),
            nn.Linear(64, 64),
            nn.ReLU(),
            nn.Linear(64, output_size),
        )

    def forward(self, x):
        return self.net(x)


def _list_model_candidates(models_dir="models"):
    if not os.path.exists(models_dir):
        return []

    files = sorted(os.listdir(models_dir))
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

    return [os.path.join(models_dir, f) for f in preferred]


def _select_model_path():
    candidates = _list_model_candidates("models")
    print("MODEL FILES FOUND:")
    for candidate in candidates:
        print(candidate)
    selected = candidates[0] if candidates else MODEL_PATH
    print("SELECTED MODEL:", selected)
    return selected


def load_dqn_model(model_path=None):
    """Load the trained DQN model from state dict or serialized module."""
    model_path = model_path or _select_model_path()

    if not os.path.exists(model_path):
        print(f"⚠️  DQN model not found at {model_path}")
        return None

    try:
        checkpoint = torch.load(model_path, map_location='cpu')

        if isinstance(checkpoint, nn.Module):
            model = checkpoint
            model.eval()
            print(f"✅ DQN MODEL LOADED: {model_path}")
            print("MODEL TYPE:", type(model))
            print("✅ MODEL READY FOR INFERENCE")
            return model

        if isinstance(checkpoint, dict):
            keys = list(checkpoint.keys())
            if any(k.startswith('net.') for k in keys):
                first_weight = checkpoint.get('net.0.weight')
                input_size = int(first_weight.shape[1]) if hasattr(first_weight, 'shape') and len(first_weight.shape) == 2 else 14
                model = SequentialDQN(input_size=input_size)
                model.load_state_dict(checkpoint)
            elif any(k.startswith('fc1') or k.startswith('fc2') or k.startswith('fc3') for k in keys):
                model = TrafficRLAgent()
                model.load_state_dict(checkpoint)
            else:
                raise RuntimeError('Unsupported checkpoint key format')

            model.eval()
            if hasattr(model, 'epsilon'):
                model.epsilon = MODEL_EPSILON
            print(f"✅ DQN MODEL LOADED: {model_path}")
            print("MODEL TYPE:", type(model))
            print("✅ MODEL READY FOR INFERENCE")
            return model

        raise RuntimeError(f"Unsupported checkpoint object type: {type(checkpoint)}")

    except Exception as e:
        print("❌ ERROR LOADING MODEL:", e)
        print("❌ MODEL STILL NOT LOADED")
        return None


SELECTED_MODEL_PATH = _select_model_path()

# Load DQN model at module startup
dqn_model = load_dqn_model(SELECTED_MODEL_PATH)
if dqn_model is None:
    print("MODEL LOADED: NO")
    print("MODEL PATH USED:", SELECTED_MODEL_PATH)
else:
    print("MODEL LOADED: YES")
    print("MODEL PATH USED:", SELECTED_MODEL_PATH)


def prepare_lane_dict(lane_dict):
    prepared = {}
    for lane_id in LANE_ORDER:
        lane = lane_dict.get(lane_id, {})
        if not isinstance(lane, dict):
            print(f"[RL STATE WARNING][inference] lane={lane_id} must be a dict, got {type(lane).__name__}")
            lane = {}
        required_keys = {'count', 'avgWaitTime', 'hasAmbulance'}
        missing = required_keys.difference(lane.keys())
        extra = set(lane.keys()).difference(required_keys)
        if missing or extra:
            print(f"[RL STATE WARNING][inference] lane={lane_id} missing={sorted(missing)} extra={sorted(extra)}")
        prepared[lane_id] = {
            'count': int(lane.get('count', 0) or 0),
            'avgWaitTime': float(lane.get('avgWaitTime', 0.0) or 0.0),
            'hasAmbulance': bool(lane.get('hasAmbulance', False)),
        }
    return prepared


def build_lane_metrics(lane_dict):
    """Build metrics dictionary for each lane."""
    lane_dict = prepare_lane_dict(lane_dict)
    metrics = {}
    for lane_id in LANE_ORDER:
        lane = lane_dict.get(lane_id, {})
        metrics[lane_id] = {
            "count": lane.get('count', 0),
            "avgWaitTime": lane.get('avgWaitTime', 0),
            "hasAmbulance": lane.get('hasAmbulance', False)
        }
    return metrics


def prepare_state_vector(lane_dict, expected_input_size=12):
    """
    Convert lane state dictionary to 12-element feature vector for DQN model.
    State vector: [count_n, has_ambulance_n, wait_n, count_e, has_ambulance_e, wait_e, ...]
    Total: 3 features × 4 lanes = 12 features
    """
    state_vector = []
    for lane_id in LANE_ORDER:
        lane = lane_dict.get(lane_id, {})
        state_vector.append(float(lane.get('count', 0) or 0.0))
        state_vector.append(1.0 if lane.get('hasAmbulance') else 0.0)
        state_vector.append(float(lane.get('avgWaitTime', 0.0) or 0.0))
    expected_input_size = int(expected_input_size or 12)
    if expected_input_size >= 14:
        wait_n = float(lane_dict.get('north', {}).get('avgWaitTime', 0.0) or 0.0)
        wait_s = float(lane_dict.get('south', {}).get('avgWaitTime', 0.0) or 0.0)
        wait_e = float(lane_dict.get('east', {}).get('avgWaitTime', 0.0) or 0.0)
        wait_w = float(lane_dict.get('west', {}).get('avgWaitTime', 0.0) or 0.0)
        state_vector.extend([
            (wait_n - wait_s) / 100.0,
            (wait_e - wait_w) / 100.0,
        ])

    if len(state_vector) > expected_input_size:
        state_vector = state_vector[:expected_input_size]
    elif len(state_vector) < expected_input_size:
        state_vector.extend([0.0] * (expected_input_size - len(state_vector)))

    return state_vector


def compute_reward(lane_dict):
    """Compute reward: minimize total wait time, priority for ambulances."""
    total_wait = 0.0
    ambulance_penalty = 0.0
    for lane_id in LANE_ORDER:
        lane = lane_dict.get(lane_id, {})
        wait_time = float(lane.get('avgWaitTime', 0.0) or 0.0)
        total_wait += wait_time
        if lane.get('hasAmbulance'):
            ambulance_penalty += wait_time * 2.0
    return -(total_wait + ambulance_penalty)


def run_inference(lane_state):
    """
    DQN neural network-based traffic control inference.
    Uses trained DQN model to select the best lane.
    """
    if not isinstance(lane_state, dict):
        print(f"[RL STATE WARNING][inference] expected lane_state dict, got {type(lane_state).__name__}")
        lane_state = {}

    lane_dict = lane_state
    lane_dict = prepare_lane_dict(lane_dict)
    
    expected_input_size = 12
    if dqn_model is not None:
        if hasattr(dqn_model, 'input_size'):
            expected_input_size = int(getattr(dqn_model, 'input_size'))
        elif hasattr(dqn_model, 'net') and len(dqn_model.net) > 0 and hasattr(dqn_model.net[0], 'in_features'):
            expected_input_size = int(dqn_model.net[0].in_features)
        elif hasattr(dqn_model, 'fc1') and hasattr(dqn_model.fc1, 'in_features'):
            expected_input_size = int(dqn_model.fc1.in_features)

    # Prepare state vector for model
    state_vector = prepare_state_vector(lane_dict, expected_input_size=expected_input_size)
    reward = compute_reward(lane_dict)
    
    # Check if model is loaded
    if dqn_model is None:
        print("❌ DQN MODEL NOT LOADED - using random action")
        selected_lane = np.random.choice(LANE_ORDER)
        model_output = None
        model_scores = {lane_id: 0.0 for lane_id in LANE_ORDER}
        selected_q_value = 0.0
        decision_reason = "Model not loaded (fallback to random)"
    else:
        # Convert to tensor (1D: 12 features for DQN)
        state_tensor = torch.FloatTensor(state_vector).unsqueeze(0)
        
        try:
            # Run model inference
            with torch.no_grad():
                output = dqn_model(state_tensor)
            
            # Get action (highest Q-value)
            output_np = output.cpu().numpy().squeeze()
            action_index = int(np.argmax(output_np))
            selected_lane = LANE_ORDER[action_index]
            
            # Create scores from model output
            model_scores = {
                lane_id: round(float(output_np[i]), 4)
                for i, lane_id in enumerate(LANE_ORDER)
            }
            selected_q_value = float(output_np[action_index])
            model_output = output_np.tolist()
            decision_reason = f"DQN predicted {selected_lane} (action_index={action_index})"
            
            print(f"🤖 DQN ACTION: {selected_lane} | Q-VALUES: {model_output} | REWARD: {round(reward, 4)}")
            
        except Exception as e:
            print(f"❌ DQN inference failed: {e} - using random action")
            selected_lane = np.random.choice(LANE_ORDER)
            model_output = None
            model_scores = {lane_id: 0.0 for lane_id in LANE_ORDER}
            selected_q_value = 0.0
            decision_reason = f"DQN inference error: {str(e)}"
    
    return {
        "lane": selected_lane,
        "duration": GREEN_DURATION,
        "debug": {
            "strategy": "dqn_model",
            "source": "DQN",
            "decision_reason": decision_reason,
            "selected_lane_score": model_scores.get(selected_lane, 0.0),
            "lane_scores": model_scores,
            "masked_out_lanes": [],
            "lane_metrics": build_lane_metrics(lane_dict),
            "reward": round(float(reward), 4),
            "state": state_vector,
            "q_value": round(float(selected_q_value), 4),
            "model_output": model_output,
        }
    }
