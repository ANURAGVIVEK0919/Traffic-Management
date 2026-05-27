"""
Signal Controller — Neural Network for green-phase duration prediction.

Architecture: Linear(13, 32) → ReLU → Linear(32, 16) → ReLU → Linear(16, 1) → Sigmoid
Output is scaled to [MIN_GREEN, MAX_GREEN] seconds.

Constraints C2 (max 30s) and C5 (min 8s) are enforced as hard clamps AFTER model output.
Constraints C1, C3, C4, C6 are enforced by the frontend FSM — not this model's concern.
"""

import os
import torch
import torch.nn as nn
from backend.core.utils.fusion import get_fused_ambulance_state

MIN_GREEN = 8.0
MAX_GREEN = 30.0

LANE_ORDER = ['north', 'east', 'south', 'west']

MODEL_PATH = os.path.join(
    os.path.dirname(__file__),
    '..', '..', '..', 'models', 'signal_model.pth'
)


class SignalDurationNet(nn.Module):
    """
    Small feedforward network that predicts green-phase duration
    for the currently active lane.

    Input  : 13 normalised features
    Output : 1 value in (0, 1) → scaled to [MIN_GREEN, MAX_GREEN]
    """

    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(13, 32),
            nn.ReLU(),
            nn.Linear(32, 16),
            nn.ReLU(),
            nn.Linear(16, 1),
            nn.Sigmoid(),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        raw = self.net(x)                           # (batch, 1)  in (0, 1)
        duration = raw * (MAX_GREEN - MIN_GREEN) + MIN_GREEN  # scale to [8, 30]
        return duration


def _build_input_tensor(
    lane_counts: dict,
    wait_times: dict,
    ambulance: dict,
    current_lane: str,
) -> torch.Tensor:
    """
    Build the 13-feature input vector from a traffic state snapshot.

    Features:
      [0-3]  vehicle counts per lane, normalised by 10
      [4-7]  average wait times per lane, normalised by 30
      [8-11] ambulance presence flags (0 / 1)
      [12]   current lane index, normalised by 3
    """
    lane_idx = LANE_ORDER.index(current_lane) if current_lane in LANE_ORDER else 0

    features = []
    for lane in LANE_ORDER:
        features.append(float(lane_counts.get(lane, 0)) / 10.0)
    for lane in LANE_ORDER:
        features.append(float(wait_times.get(lane, 0.0)) / 30.0)
    for lane in LANE_ORDER:
        features.append(1.0 if ambulance.get(lane, False) else 0.0)
    features.append(lane_idx / 3.0)

    return torch.tensor([features], dtype=torch.float32)   # shape (1, 13)


# ── Module-level model singleton ────────────────────────────────────────────
_model: SignalDurationNet | None = None
_model_loaded: bool = False


def _load_model() -> SignalDurationNet:
    global _model, _model_loaded
    if _model_loaded:
        return _model

    model = SignalDurationNet()
    path = os.path.abspath(MODEL_PATH)

    if os.path.exists(path):
        try:
            state = torch.load(path, map_location='cpu', weights_only=True)
            model.load_state_dict(state)
            print(f"[SignalController] Loaded trained model from {path}")
        except Exception as exc:
            print(f"[SignalController] WARNING — could not load model weights: {exc}")
            print("[SignalController] Falling back to untrained model (random weights).")
    else:
        print(f"[SignalController] No model file at {path} — using untrained fallback.")

    model.eval()
    _model = model
    _model_loaded = True
    return model


def predict_duration(
    lane_counts: dict,
    wait_times: dict,
    ambulance: dict,
    current_lane: str,
    gps_data: dict = None,
    audio_levels: dict = None,
) -> float:
    """
    Predict green-phase duration for the current lane.

    Returns a float in [MIN_GREEN, MAX_GREEN].

    Hard constraints applied here (C2 + C5):
      - duration >= MIN_GREEN  (8 s)
      - duration <= MAX_GREEN  (30 s)
    """
    model = _load_model()
    # Apply Multi-modal Fusion for Emergency Detection
    fused_ambulance = get_fused_ambulance_state(
        ambulance, 
        gps_data or {}, 
        audio_levels or {}
    )
    
    x = _build_input_tensor(lane_counts, wait_times, fused_ambulance, current_lane)

    with torch.no_grad():
        raw = model(x).item()

    # Hard clamp — guarantees C2 and C5 regardless of model output
    duration = max(MIN_GREEN, min(MAX_GREEN, raw))
    return round(duration, 1)
