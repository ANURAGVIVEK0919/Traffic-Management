# Quick Start - RL Training

## Prerequisites

✅ **Backend dependencies installed**:
```bash
pip install fastapi uvicorn torch pytorch
```

✅ **Video file available**:
```bash
ls uploads/video1.mp4
```

✅ **Lane calibration config**:
```bash
ls backend/perception/config/junction_demo.json
```

## Run Training

```bash
python train_rl.py
```

## What Happens

1. **Server Starts** (auto): Launches FastAPI on port 8000
2. **10 Episodes Run**: Each episode processes the entire video
3. **Models Saved**: 
   - `models/checkpoint_ep_01.pth` through `models/checkpoint_ep_10.pth`
   - `models/final_dqn_model.pth` (use this for inference)
4. **Metrics Logged**: `models/rl_logs.csv` records training progress

## Expected Output

```
======================================================================
TRAINING STARTED - RL Traffic Signal System
======================================================================
...
[EPISODE 1] Running video pipeline...
[EPISODE 1] ✓ Video pipeline completed

Episode 1 complete
  Replay buffer: 0 → 150
  Loss: 0.000000 → 13.647490
  Epsilon: 1.000000 → 0.999850

[CHECKPOINT] Saved: models\checkpoint_ep_01.pth
...
[FINAL MODEL] Saved: models\final_dqn_model.pth
[SUCCESS] Training completed successfully
```

## Key Outputs

| File | Purpose |
|------|---------|
| `final_dqn_model.pth` | Use this model for inference |
| `checkpoint_ep_*.pth` | Resume training or analyze progression |
| `rl_logs.csv` | Training metrics (reward, loss, epsilon) |

## Customization

### Different Video
```python
# In train_rl.py, line ~40
VIDEO_PATH = "uploads/my_video.mp4"
```

### More Episodes
```python
# In train_rl.py, line ~40
NUM_EPISODES = 20  # Instead of 10
```

### Faster Processing
```python
# In train_rl.py, line ~45
SAMPLE_FPS = 5  # Process more frames per second
```

## Monitor Progress

During training, you can check:

```bash
# Watch RL logs grow
tail -f models/rl_logs.csv

# Check model files created
ls -lh models/*.pth
```

## Verify Training Worked

After training completes:

```python
import torch
from pathlib import Path

# Check final model exists and has weights
model_path = Path("models/final_dqn_model.pth")
if model_path.exists():
    state_dict = torch.load(model_path)
    print(f"✓ Model loaded successfully")
    print(f"  Parameters: {len(state_dict)} weight tensors")
    print(f"  Model size: {model_path.stat().st_size / 1024:.1f} KB")
```

## Using Trained Model

### For Inference (Production)
```python
# In RL controller or inference module
import torch
model_state = torch.load("models/final_dqn_model.pth")
# Initialize DQN network and load state_dict
```

### For Fine-tuning
Load checkpoint and continue training:
```python
# Start from episode 5 checkpoint
model_state = torch.load("models/checkpoint_ep_05.pth")
# Can run more episodes to improve further
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Video not found" | Check `uploads/video1.mp4` exists |
| Server won't start | Port 8000 busy? Kill: `taskkill /F /IM pythonw.exe` |
| Training very slow | Video too long? Reduce `SAMPLE_FPS` |
| Memory error | Reduce BATCH_SIZE in `backend/controllers/rl_controller.py` |

## Help

For detailed docs, see: `TRAINING_README.md`

Quick questions? Check the training output for errors and logs in `models/rl_logs.csv`
