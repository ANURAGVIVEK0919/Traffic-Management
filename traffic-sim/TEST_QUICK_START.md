# TEST RL MODEL - QUICK REFERENCE

## One-Line Start
```bash
python test_rl_model.py
```

## What It Does (30 Second Overview)

1. ✓ Loads trained `models/final_dqn_model.pth`
2. ✓ Runs the video pipeline **with RL decisions** - collects metrics
3. ✓ Runs the video pipeline **with static baseline** - collects metrics  
4. ✓ Compares results and shows improvement %
5. ✓ Saves detailed results to `models/test_results.json`

## Expected Runtime
- **Total time**: 10-15 minutes
- **Phase 1** (RL): 5-7 minutes
- **Phase 2** (Static): 5-7 minutes
- **Reporting**: <1 minute

## Prerequisites

Before running:
```bash
# 1. Trained model must exist
ls -lh models/final_dqn_model.pth    # Should be ~24 KB

# 2. All dependencies installed
pip install -r backend/requirements.txt

# 3. Test video exists
ls -lh uploads/video1.mp4          # Should be >1 MB

# 4. Backend can start
cd backend && python main.py --test-only  # Quick test
```

## Success Indicators

```
✓ Model loaded successfully
✓ Backend ready
✓ Pipeline completed (RL phase)
✓ Pipeline completed (Static phase)
✓ Results saved
✓ Test completed successfully
```

## Typical Output Summary

```
┌─ RL MODEL RESULTS ──────────────┐
│ Avg Wait: 25.30 sec
│ Max Queue: 8 vehicles
└─────────────────────────────────┘

┌─ STATIC BASELINE RESULTS ───────┐
│ Avg Wait: 35.60 sec
│ Max Queue: 15 vehicles
└─────────────────────────────────┘

┌─ IMPROVEMENT ───────────────────┐
│ Wait Time: +28.93%
│ Max Queue: +46.67%
└─────────────────────────────────┘
```

## Key Metrics Definitions

| Metric | Meaning | Better? |
|--------|---------|---------|
| Avg Wait | Average seconds vehicles wait | Lower |
| Max Queue | Worst congestion observed | Lower |
| Improvement % | RL vs Static gain | Higher |

## Common Issues & Fixes

| Issue | Fix |
|-------|-----|
| "Model not found" | Run `python train_rl.py` first |
| "Video not found" | Check `uploads/video1.mp4` exists |
| "Port 8000 in use" | Kill process: `lsof -i :8000` |
| "No metrics collected" | Check if video processing works |
| "All results are zero" | Try different video, check backend logs |

## File References

| File | Purpose |
|------|---------|
| `test_rl_model.py` | Main testing script |
| `models/final_dqn_model.pth` | Trained model (loaded) |
| `models/test_results.json` | Results archive (saved) |
| `uploads/video1.mp4` | Test video (input) |
| `TEST_RL_MODEL_GUIDE.md` | Full documentation |

## Next Steps After Testing

```
If RL improves by >20% → Deploy to production
If RL improves by 5-20% → Consider fine-tuning
If RL improves by <5%    → Debug & retrain
```

## View Results

```bash
# See detailed results
cat models/test_results.json | python -m json.tool

# Or check the printed output from the test
```

## Troubleshooting: Step-by-Step

**Step 1: Verify prerequisites**
```bash
python -c "
import torch
from backend.controllers import rl_controller
print('✓ Imports OK')
print('✓ Model:', torch.load('models/final_dqn_model.pth'))
"
```

**Step 2: Check backend starts**
```bash
python -c "
import subprocess, time
p = subprocess.Popen(['python', '-m', 'uvicorn', 'backend.main:app', '--port', '8000'])
time.sleep(3)
p.terminate()
print('✓ Backend starts OK')
"
```

**Step 3: Verify video pipeline**
```bash
python -c "
from backend.perception.video_pipeline import run_pipeline
from pathlib import Path
result = run_pipeline(Path('uploads/video1.mp4'))
print('✓ Pipeline OK')
"
```

**Step 4: Run test**
```bash
python test_rl_model.py
```

## Performance Tips

- **Faster test**: Use shorter video clip
- **More accurate**: Use longer video (>5 min)
- **Compare fairly**: Same video for RL and Static
- **Track progress**: Keep `test_results.json` history

## Model Information

```
Model Path:        models/final_dqn_model.pth
Architecture:      DQN (14 inputs → 64 hidden → 4 outputs)
Training Episodes: 10 (from train_rl.py)
Inference Mode:    INFERENCE_MODE = True
Exploration:       ε = 0.05 (minimal randomness)
```

## Advanced: Custom Comparison

Edit in test_rl_model.py to test different policies:

```python
# Replace static_policy_decision() with:
def my_custom_policy(frame_num, state):
    # Your logic here
    return "north"  # or "south", "east", "west"
```

## Monitoring During Test

**Terminal 2** (while test runs):
```bash
# Watch backend logs
tail -f backend/logs/*.log

# Monitor system resources
htop  # or `top` on Linux
```

**Browser** (port 8000):
```
http://127.0.0.1:8000/docs  # FastAPI docs
```

## Expected vs Actual

| Expectation | Reality Check |
|-------------|---------------|
| Model loads | Should see "✓ Model loaded successfully" |
| Server starts | Should see "✓ Backend ready" |
| RL runs | Should see "✓ Metrics collected (RL)" |
| Static runs | Should see "✓ Metrics collected (STATIC)" |
| Results printed | Should see formatted comparison tables |
| JSON saved | Should see "✓ Results saved" |

## Final Checklist

- [ ] `models/final_dqn_model.pth` exists
- [ ] `uploads/video1.mp4` exists  
- [ ] Dependencies installed (`pip install -r requirements.txt`)
- [ ] Port 8000 is free
- [ ] Run: `python test_rl_model.py`
- [ ] Wait 10-15 minutes
- [ ] Check output for success message
- [ ] View results in formatted table
- [ ] Results saved to `models/test_results.json`

---

**Got issues?** See full guide: [TEST_RL_MODEL_GUIDE.md](TEST_RL_MODEL_GUIDE.md)

**Ready?** → `python test_rl_model.py`
