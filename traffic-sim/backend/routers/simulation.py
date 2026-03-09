from fastapi import APIRouter  # FastAPI router
from pydantic import BaseModel  # For request body
from backend.controllers.simulation_controller import handle_create_session, handle_submit_log, handle_get_results  # Controller imports
from typing import List, Any

router = APIRouter()  # Create router

# Request body model

class StartSimulationRequest(BaseModel):
	timer_duration: int

# Submit log request model
class SubmitLogRequest(BaseModel):
	session_id: str
	events: List[Any]

# POST route to start simulation

@router.post("/simulation/start")
def start_simulation(request: StartSimulationRequest):
	return handle_create_session(request.timer_duration)

# POST route for event log submission
@router.post("/simulation/submit-log")
def submit_log(request: SubmitLogRequest):
	return handle_submit_log(request.session_id, request.events)

# GET route for simulation results
@router.get("/simulation/results/{session_id}")
def get_results(session_id: str):
	return handle_get_results(session_id)
