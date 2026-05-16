"""
Signal router — three endpoints for the hybrid AI signal controller.

POST /signal/decision   → Neural net predicts green-phase duration
POST /signal/explain    → Gemini explains the decision in plain English (async)
POST /signal/configure  → Gemini parses natural language config commands
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.api.controllers.signal_controller import predict_duration
from backend.core.services.llm_service import explain_decision, parse_config_command

router = APIRouter(prefix="/signal", tags=["signal"])


# ── Request / Response models ────────────────────────────────────────────────

class TrafficState(BaseModel):
    lane_counts: dict = Field(default_factory=lambda: {"north": 0, "south": 0, "east": 0, "west": 0})
    wait_times:  dict = Field(default_factory=lambda: {"north": 0.0, "south": 0.0, "east": 0.0, "west": 0.0})
    ambulance:   dict = Field(default_factory=lambda: {"north": False, "south": False, "east": False, "west": False})
    current_lane: str = "north"
    elapsed_time: float = 0.0
    # Multi-modal Emergency Fusion (Point 4)
    gps_data:     dict = Field(default_factory=lambda: {"north": None, "south": None, "east": None, "west": None})
    audio_levels: dict = Field(default_factory=lambda: {"north": 0.0, "south": 0.0, "east": 0.0, "west": 0.0})


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
        gps_data=state.gps_data,
        audio_levels=state.audio_levels,
    )
    return DecisionResponse(
        recommended_duration=duration,
        current_lane=state.current_lane,
    )


@router.post("/next_decision")
def get_next_signal_decision(state: TrafficState):
    """
    DQN agent decides whether to STAY or SWITCH based on the 15-feature state.
    """
    from backend.ai.rl.agent import DQNAgent
    import os
    import numpy as np

    # 1. Build observation (15 features matching env.py)
    obs = []
    # Counts (4)
    for lane in ["north", "west", "south", "east"]:
        obs.append(state.lane_counts.get(lane, 0) / 25.0)
    # Wait Times (4)
    for lane in ["north", "west", "south", "east"]:
        obs.append(state.wait_times.get(lane, 0.0) / 80.0)
    # Ambulances (4)
    for lane in ["north", "west", "south", "east"]:
        obs.append(1.0 if state.ambulance.get(lane, False) else 0.0)
    
    # Yellow flag (1)
    obs.append(1.0 if state.elapsed_time > 25 else 0.0) 
    # Elapsed Time (1)
    obs.append(state.elapsed_time / 20.0)
    # Active Lane Index (1)
    lanes_ordered = ["north", "west", "south", "east"]
    obs.append(lanes_ordered.index(state.current_lane) / 3.0)
    
    observation = np.array(obs, dtype=np.float32)

    # 2. Load Agent
    agent = DQNAgent(15, 2)
    model_path = os.path.join("models", "dqn_indian_traffic_final.pth")
    if os.path.exists(model_path):
        try:
            agent.load(model_path)
            agent.epsilon = 0.0
        except Exception as e:
            print(f"Error loading model: {e}")
            
    # 3. Predict action (0 = Stay, 1 = Switch)
    action = agent.act(observation)
    
    if os.getenv("DEBUG_AI", "true").lower() == "true":
        print(f"🤖 [DQN] State (normed): {np.array2string(observation, precision=2, separator=',')}")
        print(f"🤖 [DQN] Action Decision: {'SWITCH' if action == 1 else 'STAY'}")

    return {"action": "switch" if action == 1 else "stay"}


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
