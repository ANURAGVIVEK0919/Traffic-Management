from fastapi import APIRouter, Query  # FastAPI router
from pydantic import BaseModel  # For request body
from backend.controllers.simulation_controller import handle_create_session, handle_submit_log, handle_get_results, handle_get_results_compare, handle_get_latest_results, handle_get_decision_logs, handle_get_session_report, handle_log_signal  # Controller imports
from typing import List, Any

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

# POST route to start simulation

@router.post("/simulation/start")
def start_simulation(request: StartSimulationRequest):
	return handle_create_session(request.timer_duration)

# POST route for event log submission
@router.post("/simulation/submit-log")
def submit_log(request: SubmitLogRequest):
	return handle_submit_log(request.session_id, request.events)


@router.post("/simulation/log")
def log_signal(request: SignalLogRequest):
	return handle_log_signal(request.session_id, request.lane, request.duration)

# GET route for simulation results
@router.get("/simulation/results/{id}")
def get_results(id: str):
	print(f"[RESULT FETCH] sessionId={id}")
	return handle_get_results(id)


@router.get("/simulation/results")
def get_results_compare(
	rl_id: str = Query(...),
	static_id: str = Query(...)
):
	print(f"[RESULT FETCH] rl_id={rl_id} static_id={static_id}")
	return handle_get_results_compare(rl_id, static_id)


@router.get("/simulation/results/latest")
def get_latest_results():
	print("[RESULT FETCH] latest live counts")
	return handle_get_latest_results()


@router.get("/simulation/decision-log/{id}")
def get_decision_log(id: str):
	print(f"[RESULT FETCH] sessionId={id}")
	return handle_get_decision_logs(id)


@router.get("/simulation/report/{id}")
def get_session_report(id: str):
	print(f"[RESULT FETCH] sessionId={id}")
	return handle_get_session_report(id)
