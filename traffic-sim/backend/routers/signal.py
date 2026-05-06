"""
Signal router — three endpoints for the hybrid AI signal controller.

POST /signal/decision   → Neural net predicts green-phase duration
POST /signal/explain    → Gemini explains the decision in plain English (async)
POST /signal/configure  → Gemini parses natural language config commands
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.controllers.signal_controller import predict_duration
from backend.services.llm_service import explain_decision, parse_config_command

router = APIRouter(prefix="/signal", tags=["signal"])


# ── Request / Response models ────────────────────────────────────────────────

class TrafficState(BaseModel):
    lane_counts: dict = Field(default_factory=lambda: {"north": 0, "south": 0, "east": 0, "west": 0})
    wait_times:  dict = Field(default_factory=lambda: {"north": 0.0, "south": 0.0, "east": 0.0, "west": 0.0})
    ambulance:   dict = Field(default_factory=lambda: {"north": False, "south": False, "east": False, "west": False})
    current_lane: str = "north"
    elapsed_time: float = 0.0


class DecisionResponse(BaseModel):
    recommended_duration: float
    current_lane: str


class ExplainRequest(TrafficState):
    decision_made: float


class ExplainResponse(BaseModel):
    explanation: str


class ConfigureRequest(BaseModel):
    command: str


class ConfigureResponse(BaseModel):
    params: dict
    acknowledged: str


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/decision", response_model=DecisionResponse)
def get_signal_decision(state: TrafficState):
    """
    Neural net predicts the recommended green-phase duration for current_lane.

    Hard constraints enforced server-side:
      - C2: duration <= 30s (MAX_GREEN)
      - C5: duration >= 8s  (MIN_GREEN) even if lane is empty
    """
    duration = predict_duration(
        lane_counts=state.lane_counts,
        wait_times=state.wait_times,
        ambulance=state.ambulance,
        current_lane=state.current_lane,
    )
    return DecisionResponse(
        recommended_duration=duration,
        current_lane=state.current_lane,
    )


@router.post("/explain", response_model=ExplainResponse)
async def get_decision_explanation(req: ExplainRequest):
    """
    Ask Gemini to explain the signal decision in plain English.
    Called asynchronously on lane switch — does not block the tick engine.
    Falls back to a rule-based explanation if GEMINI_API_KEY is not set.
    """
    explanation = await explain_decision(
        lane_counts=req.lane_counts,
        wait_times=req.wait_times,
        ambulance=req.ambulance,
        current_lane=req.current_lane,
        duration=req.decision_made,
    )
    return ExplainResponse(explanation=explanation)


@router.post("/configure", response_model=ConfigureResponse)
async def configure_controller(req: ConfigureRequest):
    """
    Parse a natural language command into signal controller parameters.
    The frontend applies the returned params to its local config store.

    Example commands:
      "give ambulances highest priority"
      "reduce max green to 20 seconds"
      "make yellow phase 8 seconds long"
    """
    result = await parse_config_command(req.command)
    return ConfigureResponse(
        params=result.get("params", {}),
        acknowledged=result.get("acknowledged", "Done."),
    )
