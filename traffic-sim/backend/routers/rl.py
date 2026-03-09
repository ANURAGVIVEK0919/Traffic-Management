
from fastapi import APIRouter
from backend.controllers.rl_controller import handle_rl_decision
from pydantic import BaseModel

router = APIRouter()

class LaneState(BaseModel):
	lane_id: str
	vehicle_count: int
	has_ambulance: bool
	avg_wait_time: float

class RLDecisionRequest(BaseModel):
	lane_states: list[LaneState]

@router.post("/rl/decision")
def rl_decision(request: RLDecisionRequest):
	return handle_rl_decision(request.dict())
