# Using the Trained RL Model

## Quick Start - Load and Predict

```python
import torch
from backend.controllers import rl_controller

# 1. Load the trained model
print("Loading trained model...")
model_weights = torch.load("models/final_dqn_model.pth")
rl_controller._q_network.load_state_dict(model_weights)

# 2. Set to inference mode (no training)
rl_controller.INFERENCE_MODE = True
rl_controller._epsilon = 0.05  # Small exploration for consistency

# 3. Make a prediction
traffic_state = {
    'line_counts': {'north': 10, 'south': 5, 'east': 8, 'west': 12},
    'wait_time_by_direction': {'north': 30, 'south': 10, 'east': 5, 'west': 40},
    'queue_length_by_direction': {'north': 2, 'south': 1, 'east': 1, 'west': 3},
    'has_ambulance_by_direction': {'north': False, 'south': False, 'east': False, 'west': False}
}

decision = rl_controller.handle_rl_decision(traffic_state)
print(f"Recommended lane: {decision['lane']}")
print(f"Duration: {decision['duration']} seconds")
```

## Deployment - As FastAPI Endpoint

The trained model is already integrated. To use it:

```bash
# 1. Ensure inference mode is enabled
# Edit backend/controllers/rl_controller.py:
#   INFERENCE_MODE = True

# 2. Load the model at startup
# Add to backend/main.py startup event:
@app.on_event("startup")
def load_trained_model():
    from backend.controllers import rl_controller
    state_dict = torch.load("models/final_dqn_model.pth")
    rl_controller._q_network.load_state_dict(state_dict)
    print("✓ Trained model loaded for inference")

# 3. Start the API server
uvicorn backend.main:app --host 0.0.0.0 --port 8000

# 4. Make requests normally
curl -X POST "http://localhost:8000/rl/decision" \
  -H "Content-Type: application/json" \
  -d '{
    "line_counts": {"north": 10, "south": 5, "east": 8, "west": 12},
    "wait_time_by_direction": {"north": 30, "south": 10, "east": 5, "west": 40},
    "queue_length_by_direction": {"north": 2, "south": 1, "east": 1, "west": 3},
    "has_ambulance_by_direction": {"north": false, "south": false, "east": false, "west": false}
  }'
```

Response:
```json
{
  "lane": "west",
  "duration": 10,
  "debug": {
    "strategy": "online_dqn",
    "action": 3,
    "action_meaning": "west",
    "reward": -15.2,
    "epsilon": 0.05,
    "replay_size": 20000,
    "loss": 5.234
  }
}
```

## Comparison - Trained vs Baseline

```python
import torch
from backend.controllers import rl_controller

def evaluate_model(model_path, scenarios):
    """Test model on various traffic scenarios"""
    
    # Load model
    state_dict = torch.load(model_path)
    rl_controller._q_network.load_state_dict(state_dict)
    rl_controller.INFERENCE_MODE = True
    
    results = []
    for scenario in scenarios:
        decision = rl_controller.handle_rl_decision(scenario)
        results.append({
            'input': scenario,
            'decision': decision['lane'],
            'reward': decision['debug']['reward']
        })
    
    return results

# Scenario 1: Heavy west traffic
scenario_1 = {
    'line_counts': {'north': 2, 'south': 1, 'east': 1, 'west': 20},
    'wait_time_by_direction': {'north': 5, 'south': 3, 'east': 2, 'west': 120},
    'queue_length_by_direction': {'north': 1, 'south': 0, 'east': 0, 'west': 5},
    'has_ambulance_by_direction': {'north': False, 'south': False, 'east': False, 'west': False}
}

# Scenario 2: Ambulance from north
scenario_2 = {
    'line_counts': {'north': 5, 'south': 5, 'east': 5, 'west': 5},
    'wait_time_by_direction': {'north': 20, 'south': 20, 'east': 20, 'west': 20},
    'queue_length_by_direction': {'north': 1, 'south': 1, 'east': 1, 'west': 1},
    'has_ambulance_by_direction': {'north': True, 'south': False, 'east': False, 'west': False}
}

# Test
results_trained = evaluate_model("models/final_dqn_model.pth", [scenario_1, scenario_2])
results_baseline = evaluate_model("models/checkpoint_ep_01.pth", [scenario_1, scenario_2])

print("Trained vs Early Checkpoint:")
for i, (trained, baseline) in enumerate(zip(results_trained, results_baseline)):
    print(f"\nScenario {i+1}:")
    print(f"  Trained decision: {trained['decision']} (reward: {trained['reward']:.2f})")
    print(f"  Baseline decision: {baseline['decision']} (reward: {baseline['reward']:.2f})")
```

## Integration with Video Pipeline

```python
from backend.perception.video_pipeline import run_pipeline
from pathlib import Path

# Ensure model is loaded first
import torch
from backend.controllers import rl_controller

state_dict = torch.load("models/final_dqn_model.pth")
rl_controller._q_network.load_state_dict(state_dict)
rl_controller.INFERENCE_MODE = True

# Now run video pipeline - will use trained model for decisions
run_pipeline(
    video_path=Path("uploads/test_video.mp4"),
    config_path=Path("backend/perception/config/junction_demo.json"),
    base_url="http://localhost:8000",
    sample_fps=2,
    preview=True  # Show decisions in real-time
)
```

## Ensemble Methods - Compare Multiple Models

```python
import torch
from backend.controllers import rl_controller

def get_ensemble_decision(state, models_to_vote):
    """Average decisions from multiple models"""
    
    votes = []
    rewards = []
    
    for model_path in models_to_vote:
        # Load model
        state_dict = torch.load(model_path)
        rl_controller._q_network.load_state_dict(state_dict)
        rl_controller.INFERENCE_MODE = True
        
        # Get decision
        decision = rl_controller.handle_rl_decision(state)
        action_idx = decision['debug']['action']
        reward = decision['debug']['reward']
        
        votes.append(action_idx)
        rewards.append(reward)
    
    # Vote by majority
    from collections import Counter
    best_action = Counter(votes).most_common(1)[0][0]
    avg_reward = sum(rewards) / len(rewards)
    
    ACTIONS = ['north', 'south', 'east', 'west']
    return ACTIONS[best_action], avg_reward

# Test with different checkpoints
test_state = {
    'line_counts': {'north': 10, 'south': 5, 'east': 8, 'west': 12},
    'wait_time_by_direction': {'north': 30, 'south': 10, 'east': 5, 'west': 40},
    'queue_length_by_direction': {'north': 2, 'south': 1, 'east': 1, 'west': 3},
    'has_ambulance_by_direction': {'north': False, 'south': False, 'east': False, 'west': False}
}

models = [
    "models/checkpoint_ep_05.pth",
    "models/checkpoint_ep_08.pth", 
    "models/final_dqn_model.pth"
]

ensemble_action, ensemble_reward = get_ensemble_decision(test_state, models)
print(f"Ensemble decision: {ensemble_action} (avg reward: {ensemble_reward:.2f})")
```

## Monitoring Model Performance

```python
import csv
from datetime import datetime

class ModelMonitor:
    def __init__(self, log_file="models/inference_log.csv"):
        self.log_file = log_file
        self.write_header()
    
    def write_header(self):
        with open(self.log_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'timestamp', 'decision', 'reward', 'epsilon', 'west_wait', 'north_count'
            ])
            writer.writeheader()
    
    def log_decision(self, decision_dict):
        """Log each decision made by trained model"""
        with open(self.log_file, 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'timestamp', 'decision', 'reward', 'epsilon', 'west_wait', 'north_count'
            ])
            
            debug = decision_dict['debug']
            writer.writerow({
                'timestamp': datetime.now().isoformat(),
                'decision': decision_dict['lane'],
                'reward': round(debug.get('reward', 0), 4),
                'epsilon': round(debug.get('epsilon', 0), 4),
                'west_wait': debug.get('wait_time_by_direction', {}).get('west', 0),
                'north_count': debug.get('counts', {}).get('north', 0),
            })

# Use in FastAPI
monitor = ModelMonitor()

from fastapi import FastAPI
app = FastAPI()

@app.post("/rl/decision")
async def rl_decision(request_dict):
    from backend.controllers import rl_controller
    decision = rl_controller.handle_rl_decision(request_dict)
    monitor.log_decision(decision)
    return decision
```

## Performance Tuning

### Disable Training Features in Inference
```python
# For maximum speed, disable features not needed:
rl_controller.INFERENCE_MODE = True    # Don't update replay buffer
rl_controller._epsilon = 0.0           # Pure greedy (no random exploration)
rl_controller.DEBUG = False            # Disable debug logging
```

### Batch Processing
```python
import torch
import numpy as np

def batch_predict(states_list):
    """Make predictions for multiple states at once (faster)"""
    
    predictions = []
    
    for state_dict in states_list:
        decision = rl_controller.handle_rl_decision(state_dict)
        predictions.append({
            'lane': decision['lane'],
            'reward': decision['debug']['reward']
        })
    
    return predictions

# Test
batch_size = 100
states = [
    {
        'line_counts': {'north': np.random.randint(0,20), 'south': np.random.randint(0,20), 
                       'east': np.random.randint(0,20), 'west': np.random.randint(0,20)},
        'wait_time_by_direction': {'north': np.random.poisson(30), 'south': np.random.poisson(30),
                                  'east': np.random.poisson(30), 'west': np.random.poisson(30)},
        'queue_length_by_direction': {'north': np.random.randint(0,5), 'south': np.random.randint(0,5),
                                     'east': np.random.randint(0,5), 'west': np.random.randint(0,5)},
        'has_ambulance_by_direction': {'north': False, 'south': False, 'east': False, 'west': False}
    }
    for _ in range(batch_size)
]

predictions = batch_predict(states)
print(f"Processed {len(predictions)} predictions in batch")
```

## Debugging Model Decisions

```python
import torch

def explain_decision(state_dict):
    """Understand why model made a particular decision"""
    
    from backend.controllers import rl_controller
    
    # Get decision
    decision = rl_controller.handle_rl_decision(state_dict)
    
    # Get Q-values for all actions
    state_normalized = rl_controller._build_state_vector(state_dict)
    state_smooth = rl_controller.stabilize_state(state_normalized)
    state_smooth = rl_controller.ema_smooth(state_smooth)
    
    state_tensor = torch.tensor(state_smooth, dtype=torch.float32).unsqueeze(0).to(rl_controller._device)
    q_values = rl_controller._q_network(state_tensor).detach().cpu().numpy()[0]
    
    ACTIONS = ['north', 'south', 'east', 'west']
    
    print("\nDecision Explanation:")
    print(f"Input state: {state_dict}")
    print(f"\nNormalized state: {state_normalized}")
    print(f"Smoothed state: {state_smooth}")
    print(f"\nQ-values for each action:")
    for action, q_val in zip(ACTIONS, q_values):
        marker = "← SELECTED" if action == decision['lane'] else ""
        print(f"  {action:6s}: {q_val:8.4f} {marker}")
    print(f"\nDecision: {decision['lane']} for {decision['duration']} seconds")
    print(f"Reward: {decision['debug']['reward']:.4f}")

# Use it
test_state = {
    'line_counts': {'north': 10, 'south': 5, 'east': 8, 'west': 12},
    'wait_time_by_direction': {'north': 30, 'south': 10, 'east': 5, 'west': 40},
    'queue_length_by_direction': {'north': 2, 'south': 1, 'east': 1, 'west': 3},
    'has_ambulance_by_direction': {'north': False, 'south': False, 'east': False, 'west': False}
}

explain_decision(test_state)
```

## Continuous Improvement

```python
def online_training_mode():
    """Enable continuous learning during deployment"""
    
    from backend.controllers import rl_controller
    
    # Load trained model
    state_dict = torch.load("models/final_dqn_model.pth")
    rl_controller._q_network.load_state_dict(state_dict)
    
    # Enable training but keep epsilon low for consistency
    rl_controller.INFERENCE_MODE = False  # Training active
    rl_controller._epsilon = 0.05         # Minimal exploration
    rl_controller.MIN_REPLAY_SIZE = 100   # Retrain on small batches
    
    # Now decisions will train the model incrementally
    # Periodically save improvements:
    # torch.save(rl_controller._q_network.state_dict(), "models/deployed_improved.pth")

def fine_tune_on_new_data(video_paths):
    """Fine-tune model on new videos"""
    
    from backend.perception.video_pipeline import run_pipeline
    from backend.controllers import rl_controller
    
    # Load trained model
    state_dict = torch.load("models/final_dqn_model.pth")
    rl_controller._q_network.load_state_dict(state_dict)
    rl_controller.INFERENCE_MODE = False  # Enable training
    
    # Train on new videos
    for video_path in video_paths:
        print(f"Fine-tuning on {video_path}")
        run_pipeline(
            video_path=video_path,
            config_path="backend/perception/config/junction_demo.json",
            base_url="http://localhost:8000",
            sample_fps=3
        )
    
    # Save fine-tuned model
    torch.save(rl_controller._q_network.state_dict(), "models/fine_tuned_v1.pth")
    print("✓ Fine-tuning complete, model saved")
```

## Summary of Usage Patterns

| Use Case | Code |
|----------|------|
| Load and predict | `state_dict = torch.load(...); model.load_state_dict(state_dict)` |
| Deploy as API | Set INFERENCE_MODE=True; start FastAPI server |
| Compare models | Load different .pth files and vote |
| Monitor performance | Log decisions to CSV for later analysis |
| Debug decisions | Get Q-values and compare action scores |
| Continuous learning | Set INFERENCE_MODE=False during inference |
| Fine-tune on new data | Load model, run more episodes on new videos |

---

**Status**: ✅ Ready for production inference

**Next**: Load `models/final_dqn_model.pth` and start using for traffic signal control!
