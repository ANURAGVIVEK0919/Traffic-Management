# RL Traffic Signal Training Script - Complete Documentation

## Overview

`train_rl.py` is a complete training orchestration script that:
- Automatically starts the FastAPI backend server
- Runs multiple training episodes using real video data  
- Feeds video frames through the entire perception and RL pipeline
- Continuously trains the DQN model across episodes
- Saves model checkpoints after each episode
- Saves the final trained model
- Logs training progress and metrics

## Architecture

### Training Loop Process

```
START SERVER
    ↓
FOR EACH EPISODE (1-10):
    │
    ├─ Save training stats (before)
    ├─ Run video pipeline (perceive → detect → decide)
    │   └─ Each frame triggers /rl/decision endpoint
    │      └─ Updates replay buffer, trains DQN model
    ├─ Save checkpoint (checkpoint_ep_NN.pth)
    ├─ Print episode summary
    └─ Delay 1 second
    │
SAVE FINAL MODEL (final_dqn_model.pth)
PRINT TRAINING SUMMARY
STOP SERVER
```

### Key Component Interactions

1. **FastAPI Server** (started automatically)
   - Runs on `http://127.0.0.1:8000`
   - Provides `/rl/decision` endpoint for traffic signal decisions
   - Manages simulation sessions

2. **Video Pipeline**  
   - Loads video from `uploads/video1.mp4`
   - Extracts frames at specified FPS (default: 3 FPS)
   - Runs YOLO vehicle detection on each frame
   - Computes lane state (vehicle counts, wait times, queues)
   - Makes HTTP POST to `/rl/decision` endpoint

3. **RL Controller**
   - Receives traffic state from video pipeline
   - Normalizes state input to 14-dimensional vector
   - Applies EMA smoothing and anti-flicker stabilization
   - Selects action using epsilon-greedy policy
   - Stores transition in replay buffer
   - Triggers training step when buffer reaches MIN_REPLAY_SIZE

4. **DQN Training**
   - Maintains replay buffer of experience tuples (state, action, reward, next_state)
   - Trains on random minibatches (BATCH_SIZE=32)
   - Computes TD error and backpropagates loss
   - Updates epsilon for exploration decay
   - Saves model checkpoints

## Configuration

Edit these constants in `train_rl.py`:

```python
NUM_EPISODES = 10              # Number of training episodes
VIDEO_PATH = "uploads/video1.mp4"   # Your training video
CONFIG_PATH = "backend/perception/config/junction_demo.json"  # Lane calibration config
BASE_URL = "http://127.0.0.1:8000"  # Backend API endpoint
SAMPLE_FPS = 3                 # How often to make RL decisions (frames per second)
CHECKPOINT_DIR = Path("models") # Where to save trained models
```

## Running Training

```bash
python train_rl.py
```

Output:
```
======================================================================
TRAINING STARTED - RL Traffic Signal System
======================================================================
  Episodes:         10
  Video:            uploads/video1.mp4
  Config:           backend/perception/config/junction_demo.json
  Sample FPS:       3
  Base URL:         http://127.0.0.1:8000
  Checkpoint Dir:   models
======================================================================

[VIDEO] Found: uploads/video1.mp4
[CONFIG] Found: backend/perception/config/junction_demo.json
[SERVER] Starting FastAPI backend...
[SERVER] ✓ Backend server is running

[EPISODE 1] Starting...
[EPISODE 1] Stats before: buffer=0, loss=0.000000, epsilon=1.000000
[EPISODE 1] Running video pipeline...
[EPISODE 1] ✓ Video pipeline completed

======================================================================
Episode 1 complete
======================================================================
  Replay buffer:       0 →   149
  Loss:             0.000000 →  13.647490
  Epsilon:          1.000000 →  0.999850
  Transitions:      +149
======================================================================

[CHECKPOINT] Saved: models\checkpoint_ep_01.pth
...
```

## Output Files

After training completes, you'll have:

```
models/
├── final_dqn_model.pth        # Final trained model (can be used for inference)
├── checkpoint_ep_01.pth       # Checkpoint after episode 1
├── checkpoint_ep_02.pth       # Checkpoint after episode 2
├── ...
├── checkpoint_ep_10.pth       # Checkpoint after episode 10
└── rl_logs.csv                # Timestep-level training logs (reward, loss, epsilon, action)
```

## Training Metrics

### Tracked Per Episode:
- **Replay Buffer Size**: Number of stored experiences
- **Loss**: DQN training loss (MSE of Q-value predictions vs targets)
- **Epsilon**: Exploration rate (starts at 1.0, decays to MIN=0.1)
- **Transitions Added**: New (state, action, reward, next_state) tuples

### Expected Behavior Across Episodes:

1. **Episode 1**:
   - Buffer starts at 0
   - After first video: ~100-300 transitions collected
   - Loss starts at 0.0 (not enough data)
   - Once buffer ≥ MIN_REPLAY_SIZE=100, loss becomes non-zero

2. **Episodes 2-10**:
   - Replay buffer continues growing (cumulative across episodes)
   - Loss generally decreases as model learns better value estimates
   - Epsilon slowly decays (EPSILON_DECAY=0.995 per step)
   - Model weights update each training step

## Restoration and Inference

To load the trained model for inference:

```python
import torch
from backend.agent.inference import run_inference

# Load final trained model
model_state = torch.load("models/final_dqn_model.pth")
# Then set this in inference module or RL controller

# Or load specific checkpoint
model_state = torch.load("models/checkpoint_ep_05.pth")
```

## Troubleshooting

### Issue: Server fails to start
- Ensure port 8000 is available (no other service running)
- Check that FastAPI dependencies are installed: `pip install fastapi uvicorn`

### Issue: Video not found
- Verify video path exists: `ls uploads/video1.mp4`
- Ensure absolute/relative path is correct in VIDEO_PATH

### Issue: Replay buffer remains 0
- Check that video pipeline is properly calling `/rl/decision` endpoint
- Verify RL controller is in training mode: `INFERENCE_MODE = False`
- Check server logs for HTTP errors

### Issue: Loss is always 0.0
- This is normal until replay buffer reaches MIN_REPLAY_SIZE (100 transitions)
- Longer videos or multiple episodes will fill this up

### Issue: Training hangs
- Video processing can be slow depending on video length
- Check that YOLO detector is warmed up
- Monitor memory usage (can spike during large batch processing)

## Advanced Usage

### Custom Video
Replace video path and ensure corresponding calibration config exists:

```python
VIDEO_PATH = "uploads/my_video.mp4"
CONFIG_PATH = "backend/perception/config/my_junction.json"
```

Generate config with: 
```bash
python -m backend.perception.calibrate_lanes_polygon \
    --video uploads/my_video.mp4 \
    --output backend/perception/config/my_junction.json
```

### Adjusting Episode Count
```python
NUM_EPISODES = 20  # Run 20 episodes instead of 10
```

### Saving More Frequently
Modify the checkpoint saving logic to save every N episodes:

```python
# After training loop completes
if episode % 2 == 0:  # Save every 2 episodes
    save_checkpoint(episode)
```

## Implementation Details

### State Vector (14-dimensional)
```
[count_north, count_south, count_east, count_west,           # 4: vehicle counts
 wait_north, wait_south, wait_east, wait_west,               # 4: average wait times
 queue_north, queue_south, queue_east, queue_west,           # 4: queue lengths
 directional_diff_ns, directional_diff_ew]                   # 2: wait time differences
```

### Preprocessing Pipeline
```
Raw State → Normalization → Stabilization (anti-flicker) → EMA Smoothing → Action Selection
```

### Training Configuration
- **Network**: 2-layer MLP (14 → 64 → 4)
- **Optimizer**: Adam (lr=0.001)
- **Discount Factor (γ)**: 0.95
- **Batch Size**: 32
- **Replay Buffer Capacity**: 20,000 experiences
- **Min Buffer Size**: 100 (start training when buffer reaches this)
- **Update Frequency**: Every step (TRAIN_EVERY_N_STEPS=1)

## Performance Notes

- Each episode processes the entire video at specified FPS
- Default 3 FPS on a ~20-minute video = ~3,600 frames = ~3,600 RL decisions
- Each decision triggers perception pipeline (YOLO detection + tracking)
- Training step adds ~2-5ms per decision
- Full 10-episode run typically takes 30-60 minutes depending on hardware

## Validation

After training, verify the model works:

```python
from backend.controllers.rl_controller import handle_rl_decision

# Test decision with synthetic state
test_state = {
    'line_counts': {'north': 10, 'south': 5, 'east': 8, 'west': 12},
    'wait_time_by_direction': {'north': 30, 'south': 10, 'east': 5, 'west': 40},
    'queue_length_by_direction': {'north': 2, 'south': 1, 'east': 1, 'west': 3},
    'has_ambulance_by_direction': {'north': False, 'south': False, 'east': False, 'west': False}
}

decision = handle_rl_decision(test_state)
print(f"Recommended action: {decision['lane']}")
```

## Files Modified/Created

- ✅ **Created**: `train_rl.py` (this training script)
- ✅ **No modifications** to existing backend or API code
- ✅ **No modifications** to perception pipeline
- ✅ **Models saved** in `models/` directory
- ✅ **Logs updated** in `models/rl_logs.csv`

## Next Steps

1. **Real Deployment**: Use `final_dqn_model.pth` in production by loading in inference mode
2. **Fine-tuning**: Run more episodes with different videos to improve generalization
3. **Evaluation**: Test on unseen video data to measure performance improvements
4. **Comparison**: Compare trained model performance vs baselines (fixed timing, heuristics, etc.)

## References

- DQN Paper: [Human-level control through deep reinforcement learning (Mnih et al., 2015)](https://www.nature.com/articles/nature14236)
- PyTorch: https://pytorch.org/
- FastAPI: https://fastapi.tiangolo.com/
- YOLO: https://github.com/ultralytics/yolov8
