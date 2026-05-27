from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, Request  # FastAPI router
from fastapi.responses import StreamingResponse
from pydantic import BaseModel  # For request body
from backend.api.controllers.simulation_controller import (
    handle_create_session,
    handle_submit_log,
    handle_get_results,
    handle_get_results_compare,
    handle_get_latest_results,
    handle_get_decision_logs,
    handle_get_session_report,
    handle_log_signal,
    latest_results,
    latest_results_lock
)
from typing import List, Any, Dict
import asyncio

# Configuration
DEBUG = False

router = APIRouter()  # Create router

# Request body model

class StartSimulationRequest(BaseModel):
	timer_duration: int

# Submit log request model
class SubmitLogRequest(BaseModel):
	session_id: str
	events: List[Any]


class SignalLogRequest(BaseModel):
	session_id: str
	lane: str
	duration: float

# Connection Manager for WebSockets
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, session_id: str, websocket: WebSocket):
        await websocket.accept()
        if session_id not in self.active_connections:
            self.active_connections[session_id] = []
        self.active_connections[session_id].append(websocket)
        if DEBUG: print(f"[WS] Client connected to session: {session_id}")

    def disconnect(self, session_id: str, websocket: WebSocket):
        if session_id in self.active_connections:
            if websocket in self.active_connections[session_id]:
                self.active_connections[session_id].remove(websocket)
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]
        print(f"[WS] Client disconnected from session: {session_id}")

    async def broadcast(self, session_id: str, data: dict):
        if session_id in self.active_connections:
            for connection in list(self.active_connections[session_id]):
                try:
                    if DEBUG: print(f"[WS SEND] session={session_id} data={data}")
                    await connection.send_json(data)
                except Exception:
                    pass

ws_manager = ConnectionManager()

@router.websocket("/ws/simulation/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    import os
    if DEBUG: print(f"[WS] session={session_id} connected")
    await ws_manager.connect(session_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(session_id, websocket)
    except Exception as e:
        print(f"❌ WS ERROR: {e}")


# --- VIDEO STREAMING ENDPOINTS ---
latest_frame_bytes = b""

@router.post("/simulation/video-frame")
async def receive_video_frame(request: Request):
    global latest_frame_bytes
    latest_frame_bytes = await request.body()
    return {"status": "ok"}

async def video_generator():
    while True:
        if latest_frame_bytes:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + latest_frame_bytes + b'\r\n')
        # Limit frame check rate (approx 20 FPS)
        await asyncio.sleep(0.05)

@router.get("/video_feed")
async def video_feed():
    return StreamingResponse(
        video_generator(), 
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

# POST route to start simulation

@router.post("/simulation/start")
def start_simulation(request: StartSimulationRequest):
	return handle_create_session(request.timer_duration)

# POST route for event log submission
@router.post("/simulation/submit-log")
async def submit_log(request: SubmitLogRequest):
    print(f"[API] submit session={request.session_id} events={len(request.events)}")
    result = handle_submit_log(request.session_id, request.events)
    latest_counts = handle_get_latest_results(request.session_id)
    import time
    latest_counts["timestamp"] = time.time()
    counts = latest_counts.get('lane_counts', [0,0,0,0])
    print(f"[WS] session={request.session_id} counts={counts}")
    print(f"🚀 [WS BROADCAST] session={request.session_id} data={latest_counts}")
    await ws_manager.broadcast(request.session_id, latest_counts)
    return result


@router.post("/simulation/log")
def log_signal(request: SignalLogRequest):
	return handle_log_signal(request.session_id, request.lane, request.duration)

@router.get("/simulation/results/latest")
def get_latest_results(session_id: str = Query(None)):
    data = handle_get_latest_results(session_id)
    if DEBUG:
        import os
        print(f"[API] fetch session={session_id} PID={os.getpid()}")
    return data

@router.get("/simulation/live-counts/{id}")
def get_live_counts(id: str):
    data = handle_get_latest_results(id)
    counts = data.get('lane_counts', [0, 0, 0, 0])
    print(f"📡 [API LIVE COUNTS] session={id} counts={counts}")
    return counts


@router.get("/simulation/results")
def get_results_compare(
	rl_id: str = Query(...),
	static_id: str = Query(...)
):
	print(f"[RESULT FETCH] rl_id={rl_id} static_id={static_id}")
	return handle_get_results_compare(rl_id, static_id)


# GET route for simulation results
@router.get("/simulation/results/{id}")
def get_results(id: str):
	print(f"[RESULT FETCH] sessionId={id}")
	return handle_get_results(id)


@router.get("/simulation/decision-log/{id}")
def get_decision_log(id: str):
	print(f"[RESULT FETCH] sessionId={id}")
	return handle_get_decision_logs(id)


@router.get("/simulation/report/{id}")
def get_session_report(id: str):
	print(f"[RESULT FETCH] sessionId={id}")
	return handle_get_session_report(id)
