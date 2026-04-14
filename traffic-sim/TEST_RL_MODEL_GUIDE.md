# test_rl_model.py - Model Evaluation & Comparison Guide

## Overview

`test_rl_model.py` is a comprehensive testing script that evaluates the trained RL model's performance by:

1. **Loading the trained DQN model** from `models/final_dqn_model.pth`
2. **Running video pipeline in RL mode** with the trained model making decisions
3. **Running video pipeline in static baseline mode** with a fixed signal rotation
4. **Collecting metrics** for both modes (wait times, queue lengths)
5. **Comparing performance** and computing improvement percentages
6. **Printing detailed results** showing RL vs Static comparison

## Quick Start

```bash
# Run the test
python test_rl_model.py
```

**What happens:**
1. Server starts automatically on port 8000
2. Video processes twice (RL mode, then Static baseline)
3. Metrics collected automatically
4. Results printed in formatted tables
5. Results saved to `models/test_results.json`
6. Server stops cleanly

## Expected Output

```
======================================================================
RL TRAFFIC SIGNAL MODEL - EVALUATION TEST
======================================================================

[MODEL] Loading trained model...
[MODEL] ✓ Model loaded successfully
[SERVER] Starting backend...
[SERVER] ✓ Backend ready

======================================================================
PHASE 1: RL MODEL EVALUATION
======================================================================
[RL] Running video pipeline with trained model...
[RL] ✓ Pipeline completed

======================================================================
PHASE 2: STATIC BASELINE EVALUATION
======================================================================
[STATIC] Running video pipeline with static baseline...
[STATIC] ✓ Pipeline completed

======================================================================
TEST RESULTS - RL vs STATIC BASELINE
======================================================================

┌─ RL MODEL RESULTS ─────────────────────────────────────────┐
│ Overall Avg Wait Time:        25.30 seconds
│ Max Queue Length:                  8 vehicles
│ Frames Processed:                360 
│ Decisions Made:                 360
│
│ Wait Time by Direction:
│   North:                        28.50 sec
│   South:                        22.10 sec
│   East:                         18.30 sec
│   West:                         32.40 sec
└─────────────────────────────────────────────────────────────┘

┌─ STATIC BASELINE RESULTS ──────────────────────────────────┐
│ Overall Avg Wait Time:        35.60 seconds
│ Max Queue Length:                 15 vehicles
│ Frames Processed:                360
│ Decisions Made:                 360
│
│ Wait Time by Direction:
│   North:                        42.30 sec
│   South:                        28.50 sec
│   East:                         25.40 sec
│   West:                         45.20 sec
└─────────────────────────────────────────────────────────────┘

┌─ IMPROVEMENT ANALYSIS ─────────────────────────────────────┐
│ Wait Time Improvement:         28.93%
│   ✓ RL is 28.9% faster
│
│ Max Queue Improvement:         46.67%
│   ✓ RL reduces max queue by 46.7%
└─────────────────────────────────────────────────────────────┘

SUCCESS - Test completed successfully
```

## Key Features

### ✓ Automatic Server Management
- Starts FastAPI backend automatically
- Performs health check before running tests
- Cleans up gracefully after completion

### ✓ Two-Mode Testing
1. **RL Mode**: Uses trained neural network
2. **Static Mode**: Fixed cycle (north → south → east → west)

### ✓ Comprehensive Metrics
- Average wait time (overall and by direction)
- Maximum queue length
- Frames processed & decisions made
- Total wait time aggregation
- Direction-specific analysis

### ✓ No Code Modifications
- Uses existing RL controller
- Works with existing perception pipeline
- Uses monkey-patching for static baseline (non-invasive)
- Restores original behavior after

### ✓ Detailed Reporting
- Formatted comparison tables
- Per-direction breakdown
- Improvement percentages
- Results saved to JSON

## Components

### Model Loading
```python
def load_trained_model():
    """Loads model from models/final_dqn_model.pth"""
    - Sets INFERENCE_MODE = True
    - Sets epsilon = 0.05 (minimal randomness)
    - Disables training
```

### Metrics Collection
```python
def collect_metrics(response_dict, mode='rl'):
    """Extracts metrics from RL controller responses"""
    - Wait times by direction
    - Queue lengths by direction
    - Vehicle counts
    - Decision records
```

### Static Baseline Policy
```python
def static_policy_decision(frame_num, total_frames):
    """Generates fixed signal rotation"""
    - Cycles through: north → south → east → west
    - 30-frame cycle (each light ~1 second at 2 FPS)
```

### Results Analysis
```python
def compute_averages(metrics):
    """Computes statistics from collected metrics"""
    - Average wait time overall and per direction
    - Max queue length
    - Frame and decision counts
```

### Results Reporting
```python
def print_results():
    """Prints formatted comparison"""
    - Side-by-side comparison tables
    - Improvement percentages
    - Direction-by-direction analysis
```

## Configuration

Edit at top of script:

```python
VIDEO_PATH = Path("uploads/video1.mp4")           # Video to test on
CONFIG_PATH = Path("backend/perception/config/junction_demo.json")  # Lane calibration
BASE_URL = "http://127.0.0.1:8000"                # Backend API
MODEL_PATH = Path("models/final_dqn_model.pth")   # Trained model
SAMPLE_FPS = 2                                     # Decision frequency
```

## Metrics Explained

### Wait Time
- **Definition**: Average time vehicles spend waiting at intersection
- **Unit**: Seconds
- **Lower is better**: RL should reduce wait times

### Queue Length
- **Definition**: Number of vehicles waiting at intersection
- **Unit**: Vehicles
- **Lower is better**: RL should reduce congestion

### Improvement %
- **Formula**: `(Static - RL) / Static * 100`
- **Positive**: RL is better
- **Negative**: Static is better

### By Direction Analysis
- Shows performance for each traffic direction (N/S/E/W)
- May vary based on traffic distribution in video
- Helps identify which directions benefit most from RL

## Understanding Results

### Good RL Performance (Expected)
```
✓ Wait Time Improvement: +20-40%
✓ Max Queue Improvement: +30-50%
✓ Consistent across directions
```

Indicates:
- Model learned effective traffic control
- Reduces congestion and wait times
- Generalizes well to unseen data

### Poor RL Performance (Investigate)
```
✗ Wait Time Improvement: Negative
✗ Max Queue Improvement: Negative
```

Possible causes:
- Model needs more training
- Static baseline happens to be optimal for this video
- Video has unusual traffic patterns
- Model overfitted to training data

### Mixed Results (Normal)
```
✓ Wait Time Improvement: +15%
✗ Max Queue Improvement: -5%
```

May indicate:
- Trade-offs in optimization (spread vs intensity)
- Some directions better, others worse
- Model making different strategic choices

## Output Files

### test_results.json
```json
{
  "rl": {
    "overall_avg_wait": 25.3,
    "by_direction": {
      "wait": {"north": 28.5, ...},
      "queue": {"north": 3.2, ...}
    },
    "max_queue_length": 8,
    "frames_processed": 360,
    "decisions_made": 360
  },
  "static": {...},
  "wait_improvement": 28.93,
  "queue_improvement": 46.67
}
```

Use for:
- Historical tracking of model performance
- Comparison across different models
- Automated testing pipelines
- Performance reporting

## Workflow Examples

### Single Test Run
```bash
python test_rl_model.py
```

### Compare Multiple Models
```bash
# Save final_dqn_model results
cp models/final_dqn_model.pth models/final_v1.pth
python test_rl_model.py > results_v1.txt

# Compare after improvements
cp models/final_dqn_model.pth models/final_v2.pth  
python test_rl_model.py > results_v2.txt

# Compare results_v1.txt and results_v2.txt
```

### Automated Testing
```bash
#!/bin/bash
# test_suite.sh

echo "Testing RL Model"
python test_rl_model.py

if grep -q "Improvement: [0-9]*\." models/test_results.json; then
    echo "✓ Pass: Model shows improvement"
    exit 0
else
    echo "✗ Fail: Model performance below baseline"
    exit 1
fi
```

## Troubleshooting

### Issue: "Model not found"
```
[ERROR] Model not found: models/final_dqn_model.pth
```

**Solution**: Train the model first
```bash
python train_rl.py
```

### Issue: "Video not found"
```
[ERROR] Video not found: uploads/video1.mp4
```

**Solution**: Verify video exists
```bash
ls -lh uploads/video1.mp4
```

### Issue: "Server failed to start"
```
[SERVER] ✗ Server timeout
```

**Solutions**:
- Port 8000 in use: `lsof -i :8000` then kill the process
- Dependencies missing: `pip install fastapi uvicorn`
- Memory issues: Close other applications

### Issue: "Metrics all zero"
```
Overall Avg Wait Time:             0.00 seconds
```

**Solutions**:
- Video contains no traffic: Use a different video
- Pipeline error: Check /rl/decision endpoint
- Metrics collection issue: Check `collect_metrics()` function

## Advanced Usage

### Custom Baseline
Replace `static_policy_decision()` with your own:

```python
def custom_baseline_policy(frame_num, state):
    """Your custom policy"""
    # Implement preferred baseline here
    return "north"  # or whatever
```

### Extended Metrics
Add to `collect_metrics()`:

```python
# Track additional metrics
metrics['total_stops'] = debug.get('stop_count', 0)
metrics['phase_changes'] = debug.get('phase_changes', 0)
```

### Multiple Videos
```python
for video in ['video1.mp4', 'video2.mp4', 'video3.mp4']:
    VIDEO_PATH = Path(f"uploads/{video}")
    result = main()
    print(f"\n{video}: {result['wait_improvement']:.1f}% improvement")
```

### Performance Profiling
```python
import cProfile
import pstats

profiler = cProfile.Profile()
profiler.enable()

main()

profiler.disable()
stats = pstats.Stats(profiler)
stats.print_stats(20)  # Top 20 functions
```

## Performance Notes

- **Execution time**: ~10-15 minutes (2 video runs)
- **Memory**: ~300-500 MB peak
- **CPU**: Single-threaded, uses ~50% of one core
- **GPU**: If available, will use for model inference

## Integration with CI/CD

### GitHub Actions Example
```yaml
name: RL Model Testing
on: [push]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - run: pip install -r requirements.txt
      - run: python train_rl.py  # Ensure model exists
      - run: python test_rl_model.py
      - run: python -c "import json; r=json.load(open('models/test_results.json')); exit(0 if r['wait_improvement']>0 else 1)"
```

## Best Practices

1. **Test after training**: Always run test to validate model
2. **Use consistent video**: Same test video for comparisons
3. **Document baseline**: Record static baseline result as reference
4. **Track over time**: Save results to track model improvements
5. **Multiple runs**: Average results over several test runs for stability

## Next Steps

After testing:

1. **If RL performs well** (>20% improvement):
   - Deploy to production
   - Monitor real-world performance
   - Collect new data for fine-tuning

2. **If RL performs okay** (5-20% improvement):
   - Consider hyperparameter tuning
   - Run more training episodes
   - Fine-tune on more videos

3. **If RL performs poorly** (<5% or negative):
   - Check if model loaded correctly
   - Verify inference mode enabled
   - Investigate potential issues:
     - Video too short
     - Model wasn't trained properly
     - State normalization issues
     - Training hyperparameters need adjustment

## Related Scripts

- `train_rl.py`: Train the model
- `verify_training_setup.py`: Verify system setup
- `models/test_results.json`: Test results archive

## Summary

`test_rl_model.py` provides:
- ✓ Automatic evaluation framework
- ✓ Fair comparison vs static baseline
- ✓ Comprehensive metrics collection
- ✓ Detailed result reporting
- ✓ JSON output for analysis
- ✓ Non-invasive testing (no code modifications)

**Start testing**: `python test_rl_model.py`
