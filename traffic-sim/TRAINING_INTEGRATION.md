# Training Script - Technical Integration Guide

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        train_rl.py                               │
│  (Training Orchestrator)                                         │
└──────────────┬──────────────────────────────────────────────────┘
               │
        ┌──────▼──────────────────────┐
        │  FastAPI Backend Server      │  (Started automatically)
        │  port: 127.0.0.1:8000       │
        └──────┬──────────────────────┘
               │
        ┌──────▼────────────────────────────────────────────┐
        │  run_pipeline()                                   │
        │  (Video Pipeline - backend.perception)            │
        │  - Reads video frames                             │
        │  - Detects vehicles with YOLO                     │
        │  - Computes lane state                            │
        │  - Makes HTTP POST to /rl/decision endpoint       │
        └──────┬───────────────────────────────────────────┘
               │
        ┌──────▼─────────────────────────────────────────────┐
        │  handle_rl_decision()                              │
        │  (backend.controller.rl_controller)               │
        │  - Normalizes state                               │
        │  - Applies EMA smoothing + stabilization          │
        │  - Selects action (epsilon-greedy)                │
        │  - Stores in replay buffer                        │
        │  - Trains DQN if buffer full                      │
        │  - Returns lane decision                          │
        └──────┬──────────────────────────────────────────┘
               │
        ┌──────▼──────────────────────────────┐
        │  DQN Model State (in Memory)        │
        │  - _q_network                       │
        │  - _target_network                  │
        │  - _replay_buffer (deque)           │
        │  - _epsilon                         │
        │  - _optimizer                       │
        └─────────────────────────────────────┘

After all episodes:
        │
        └──► Save state to disk
             - models/final_dqn_model.pth

Per episode:
        │
        └──► Save checkpoint
             - models/checkpoint_ep_NN.pth
```

## Code Flow - Single RL Decision

When video pipeline processes a video and makes an RL decision:

```python
# 1. Video Pipeline makes HTTP POST request
POST http://127.0.0.1:8000/rl/decision
{
    "line_counts": {"north": 10, "south": 5, ...},
    "wait_time_by_direction": {"north": 30, ...},
    "queue_length_by_direction": {"north": 2, ...},
    "has_ambulance_by_direction": {...}
}

# 2. FastAPI routes to RL router (backend/routers/rl.py)
@router.post("/rl/decision")
async def rl_decision(request_dict):
    # Calls backend.controllers.rl_controller.handle_rl_decision()
    result = handle_rl_decision(request_dict)
    return result

# 3. RL Controller processes request
def handle_rl_decision(request_dict):
    # Step A: Build normalized state (14-D vector)
    state = _build_state_vector(request_dict)
    
    # Step B: Stabilize state (anti-flicker + EMA smoothing)
    state_stabilized = stabilize_state(state)
    state_smooth = ema_smooth(state_stabilized)
    
    # Step C: Store previous transition in replay buffer
    if _prev_state is not None and _prev_action is not None:
        _replay_buffer.append((
            _prev_state,         # Previous state
            _prev_action,        # Action taken in that state
            _prev_reward,        # Reward received
            state_smooth         # New state
        ))
    
    # Step D: Update global state
    _prev_state = state_smooth
    
    # Step E: Train if buffer has enough experiences
    if len(_replay_buffer) >= MIN_REPLAY_SIZE:
        _train_step_if_ready()
        # Samples batch from replay buffer
        # Computes Q-values (current and target)
        # Computes loss = (target - current)^2
        # Backpropagates and updates weights
        # Updates epsilon for exploration decay
    
    # Step F: Select next action
    if step < 3000:  # Exploration phase
        action = random choice from [0, 1, 2, 3]
    else:            # Exploitation phase
        action = argmax of Q-values
    
    # Step G: Compute reward
    reward = compute_reward_from_current_state(...)
    
    # Step H: Store action and reward for next iteration
    _prev_action = action
    _prev_reward = reward
    
    # Step I: Return decision
    return {
        "lane": ACTIONS[action],  # "north", "south", "east", "west"
        "duration": 10,
        "debug": {...}
    }

# 4. Video pipeline receives response and continues
```

## Global State in RL Controller

These are module-level variables that persist across API calls:

```python
# Model and Training
_q_network = SignalDQN()          # Main DQN network (trained)
_target_network = SignalDQN()     # Target network (for stability)
_optimizer = optim.Adam(...)      # Gradient descent optimizer
_device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# Experience Management  
_replay_buffer = deque(maxlen=REPLAY_CAPACITY)  # Circular buffer of transitions
_prev_state = None                # Previous state (for transition storage)
_prev_action = None               # Previous action
_prev_reward = None               # Previous reward

# Training Tracking
_last_loss = 0.0                  # Latest training loss
_epsilon = EPSILON_START          # Current exploration rate

# State Preprocessing
_ema_state = None                 # Previous smoothed state (for EMA)
_last_valid_state = None          # Last non-None state (for fallback)

# Configuration
INFERENCE_MODE = False            # False = Training, True = Act only
MIN_REPLAY_SIZE = 100             # Start training after 100 experiences
BATCH_SIZE = 32                   # Minibatch size for training
LEARNING_RATE = 1e-3              # Optimizer learning rate
GAMMA = 0.95                      # Discount factor
EPSILON_START = 1.0               # Initial exploration rate
EPSILON_MIN = 0.1                 # Minimum exploration rate
EPSILON_DECAY = 0.995             # Per-step decay: ε_new = ε * 0.995
```

## Training Data Flow - Multi-Episode

```
Episode 1:
  replay_buffer = [] (empty)
  Step 1-99: Buffer filling (no training)
    - Frame 1 → State 1 → Action → Reward recorded
    - Frame 2 → State 2 → Action → Reward recorded
    - ... (no training yet)
  
  Step 100: Buffer reaches MIN_REPLAY_SIZE=100
    - Training starts
    - Sample 32 random transitions from buffer
    - Compute TD loss
    - Update weights
    - epsilon = 1.0 * 0.995^N (decaying)
  
  Step 101-N: Continue pattern
    - Store new transition
    - Train on minibatch
  
Episode 2:
  Replay buffer is NOT RESET (contains ~150-300 from Ep 1)
  - Continue accumulating experiences
  - Training continues immediately (buffer already > 100)
  - Loss likely lower than Ep 1 (model improving)
  - epsilon continues decaying
  
Episodes 3-10:
  - Buffer grows larger
  - Loss becomes more stable (convergence)
  - epsilon approaches EPSILON_MIN=0.1
  - Toward end: mostly greedy actions (exploitation)
```

## Checkpoint Saving

After each episode:

```python
save_checkpoint(episode)
# Saves _q_network.state_dict() to models/checkpoint_ep_NN.pth

# Each checkpoint is ~20 KB and contains:
# - All network weights
# - All biases
# - NO training state (no replay buffer, no optimizer state)

# Later, you can load and continue training:
import torch
state_dict = torch.load("models/checkpoint_ep_05.pth")
_q_network.load_state_dict(state_dict)
# replay buffer and optimizer state persist (or restart)
```

## Integration Points with Existing System

### 1. FastAPI Server (backend/main.py)
```python
# No changes needed - train_rl.py starts the server automatically
# The existing API endpoints work as-is:
# - POST /rl/decision ← Called by video pipeline during training
# - POST /simulation/start ← Creates session
# - POST /simulation/submit-log ← Stores results after episode
```

### 2. Video Pipeline (backend/perception/video_pipeline.py)
```python
# No changes needed - train_rl.py calls run_pipeline() 
# which makes requests to the running backend server

from backend.perception.video_pipeline import run_pipeline

run_pipeline(
    video_path=Path("uploads/video1.mp4"),
    config_path=Path("backend/perception/config/junction_demo.json"),
    base_url="http://127.0.0.1:8000",  # Points to our running server
    sample_fps=3
)
```

### 3. RL Controller (backend/controllers/rl_controller.py)
```python
# No changes needed - handle_rl_decision() already has:
# ✓ Training logic (_train_step_if_ready)
# ✓ Replay buffer management
# ✓ Epsilon decay
# ✓ Model persistence (_save_dqn_model)
# ✓ State preprocessing (stabilize_state, ema_smooth)

# train_rl.py accesses global state directly:
from backend.controllers import rl_controller

stats = {
    'replay_size': len(rl_controller._replay_buffer),
    'epsilon': rl_controller._epsilon,
    'loss': rl_controller._last_loss,
}
```

### 4. Model Saving
```python
# RL Controller periodically saves to:
MODEL_SAVE_PATH = 'models/rl_signal_dqn.pth'

# train_rl.py ADDITIONALLY saves to:
'models/final_dqn_model.pth'    # Final trained model
'models/checkpoint_ep_NN.pth'   # Checkpoints per episode
```

## Key Design Decisions

### Why Subprocess for Backend?
- Isolated process with separate stdout/stderr
- Easy to stop/start independently
- Doesn't block main training thread
- Can monitor health via HTTP health checks

### Why Restart Backend Each Run?
- Fresh database state (no carryover from previous runs)
- Clean model loading (no stale tensors)
- Guaranteed consistent state
- Option to modify between runs

### Why Persistent Replay Buffer?
- Accumulate experiences across episodes
- Earlier episodes build foundation, later episodes refine
- More efficient than restarting buffer each episode
- Mirrors how real RL systems work

### Why Global Variables in RL Controller?
- Fast access during high-frequency API calls
- Per-request context would require serialization overhead
- Training state naturally lives in module memory
- Can be saved/loaded to disk as needed

## Performance Characteristics

### Per-Episode Processing
```
Video: 20 minutes, 480 fps (depends on actual video)
Sampled at 3 FPS = ~3,600 frames processed
Per frame processing:
  - YOLO detection: ~30-50ms
  - Lane mapping: ~5ms
  - State computation: ~1ms
  - RL decision: ~5-10ms (includes training if buffer ≥ 100)
  - Total: ~50-70ms per frame
Total per episode: 3600 * 0.07 = 252 seconds ≈ 4 minutes

Full 10-episode training: ~40 minutes + server startup/shutdown overhead
```

### Memory Usage
```
DQN Model:
  - 2 networks (main + target): ~40 KB total
  - Optimizer state: ~40 KB
  - Total model: ~80 KB

Replay Buffer (20,000 capacity):
  - Each transition: ~200 bytes (4 tensors of size 14)
  - Max replay memory: 20,000 * 200 = 4 MB
  - Growing over episodes, max reached when buffer full

During training:
  - Minibatch of 32: ~6 KB
  - Computation graph: ~50 KB (temporary during backward pass)
  - Total memory: ~5-10 MB typically
```

## Extending the Training Script

### Add Custom Evaluation
```python
def evaluate_episode(episode_num):
    """Run inference-only pass to measure performance"""
    stats = run_inference_pass(video_path)
    log_evaluation(episode_num, stats)

# In training loop:
for episode in range(1, NUM_EPISODES + 1):
    run_training_episode(episode)
    evaluate_episode(episode)  # Add evaluation step
```

### Distributed Training
```python
# Run multiple training instances on different GPUs
for gpu_id in [0, 1, 2, 3]:
    run_training_on_gpu(NUM_EPISODES // 4, gpu_id)
```

### Save Training Artifacts
```python
# Log metrics to wandb/tensorboard
from tensorboard import SummaryWriter

writer = SummaryWriter("runs/training_run_1")
writer.add_scalar("loss", _last_loss, global_step)
writer.add_scalar("replay_buffer_size", len(_replay_buffer), global_step)
```

## Validation Checklist

After running `train_rl.py`:

- [ ] `models/final_dqn_model.pth` exists (>10 KB)
- [ ] `models/checkpoint_ep_01.pth` through `checkpoint_ep_10.pth` exist
- [ ] `models/rl_logs.csv` has >100 lines (training events)
- [ ] No Python errors in console output
- [ ] "SUCCESS" message printed at end
- [ ] Model can be loaded: `torch.load("models/final_dqn_model.pth")`

## Next Steps

1. **Inference**: Load `final_dqn_model.pth` and use for traffic signal control
2. **Evaluation**: Test on new unseen videos to measure generalization
3. **Hyperparameter tuning**: Adjust BATCH_SIZE, LEARNING_RATE, GAMMA for better convergence
4. **Multi-intersection**: Extend to train multiple intersections simultaneously
