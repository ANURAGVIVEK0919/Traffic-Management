# Traffic Sim Prototype

This repository contains two paths:

1. Current simulator workflow using the backend + frontend.
2. Prototype video workflow that runs detection on recorded traffic videos and feeds the existing RL decision endpoint.

## Quick Start: Current App

Run these from the project root.

### Backend

```powershell
python -m venv .venv
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned -Force
.\.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

### Frontend

```powershell
cd frontend
npm install
npm start
```

Open:

- Frontend: http://localhost:3000
- Backend docs: http://localhost:8000/docs

## Prototype Workflow: Video Only

Use recorded videos first. The pipeline reads a video file, detects vehicles, maps them to lane regions, sends lane snapshots to the existing RL endpoint, and stores results for dashboard analysis.

### 1) Install dependencies

```powershell
pip install -r backend/requirements.txt
```

### 2) Calibrate lane ROIs

**Option 1: Automatic detection (recommended)**

Auto-detect lanes using Hough line detection via OpenCV:

```powershell
python -m backend.perception.calibrate_lanes_auto --video "path/to/video.mp4" --output "backend/perception/config/junction_demo.json"
```

**Option 2: Manual rectangles**

Click to define rectangular lane regions:

```powershell
python -m backend.perception.calibrate_lanes --video "path/to/video.mp4" --output "backend/perception/config/junction_demo.json" --timer-duration 120
```

**Option 3: Manual polygons**

Click to define polygon-shaped lane regions (better for angled cameras):

```powershell
python -m backend.perception.calibrate_lanes_polygon --video "path/to/video.mp4" --output "backend/perception/config/junction_demo.json" --timer-duration 120
```

### 3) Start backend

```powershell
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

### 4) Run the video pipeline

```powershell
python -m backend.perception.video_pipeline --video "path/to/video.mp4" --config "backend/perception/config/junction_demo.json" --base-url "http://localhost:8000" --sample-fps 2 --smooth-alpha 0.6 --preview --output-video "outputs/annotated_run.mp4"
```

You can stop the preview window with `q`.

### 5) Generate a session report

After the run completes, the pipeline prints a session ID. Use it here:

```powershell
python -m backend.perception.session_report --session-id YOUR_SESSION_ID
```

JSON output:

```powershell
python -m backend.perception.session_report --session-id YOUR_SESSION_ID --json
```

## Hugging Face Model Option

The detector supports either a local YOLO model or a Hugging Face-hosted Ultralytics model.

### Local model

```powershell
$env:YOLO_MODEL_SOURCE="local"
$env:YOLO_LOCAL_MODEL_PATH="models/yolo_traffic.pt"
```

### Hugging Face model

```powershell
$env:YOLO_MODEL_SOURCE="hf"
$env:YOLO_HF_REPO_ID="Perception365/VehicleNet-Y26s"
# Optional if the filename is different:
# $env:YOLO_HF_FILENAME="weights/best.pt"
```

If the HF model is gated, log in with `huggingface-cli login` and accept the model terms first.

## Final Prototype Checklist

Use this once to verify the full video prototype loop.

1. Calibrate lane regions with a sample video.
2. Start the backend and confirm `/docs` opens.
3. Run the video pipeline with `--preview` and optionally `--output-video`.
4. Confirm a `session_id` is printed by the pipeline.
5. Open `http://localhost:3000/dashboard/<session_id>`.
6. Confirm these are visible:
	- comparison metrics
	- decision timeline
	- alert badges
	- session report summary
7. Run the session report script for the same session ID.

```powershell
python -m backend.perception.session_report --session-id YOUR_SESSION_ID
```

## Prototype Tips

- Use one video at a time until lane regions are calibrated well.
- Start with daytime clips.
- If ambulance detection is not available in the model classes, treat emergency priority as disabled until fine-tuning.
- Keep `sample-fps` low at first (`1.0` to `2.0`) for stability.
- Use the generated `session_report` to compare clips.

## Important Files

- Backend API: [backend/main.py](backend/main.py)
- RL decision endpoint: [backend/routers/rl.py](backend/routers/rl.py)
- Detector: [backend/agent/yolo_detector.py](backend/agent/yolo_detector.py)
- Video pipeline: [backend/perception/video_pipeline.py](backend/perception/video_pipeline.py)
- Auto Lane Calibration: [backend/perception/calibrate_lanes_auto.py](backend/perception/calibrate_lanes_auto.py)
- ROI calibration: [backend/perception/calibrate_lanes.py](backend/perception/calibrate_lanes.py)
- Polygon calibration: [backend/perception/calibrate_lanes_polygon.py](backend/perception/calibrate_lanes_polygon.py)
- Session report: [backend/perception/session_report.py](backend/perception/session_report.py)
- Dashboard: [frontend/src/pages/DashboardPage.jsx](frontend/src/pages/DashboardPage.jsx)
