"""
Training script for the SignalDurationNet model.

Generates 100,000 synthetic traffic scenarios and trains the network
using supervised learning with heuristic-labelled optimal durations.

Run from traffic-sim/ directory:
    python backend/train_signal_model.py

Output: models/signal_model.pth
"""

import os
import random
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
from backend.api.controllers.signal_controller import SignalDurationNet, MIN_GREEN, MAX_GREEN, LANE_ORDER

# ── Hyperparameters ──────────────────────────────────────────────────────────
NUM_SAMPLES   = 100_000
EPOCHS        = 15
BATCH_SIZE    = 256
LEARNING_RATE = 0.001
SAVE_PATH     = os.path.join(os.path.dirname(__file__), '..', 'models', 'signal_model.pth')


def generate_scenario():
    """
    Generate one random traffic scenario.
    Returns (features_13, label_duration).
    """
    counts    = {lane: random.randint(0, 12) for lane in LANE_ORDER}
    waits     = {lane: random.uniform(0, 60) for lane in LANE_ORDER}
    ambulance = {lane: random.random() < 0.05 for lane in LANE_ORDER}
    current_lane = random.choice(LANE_ORDER)
    lane_idx  = LANE_ORDER.index(current_lane)

    # ── Heuristic label ──────────────────────────────────────────────────────
    active_count   = counts[current_lane]
    active_wait    = waits[current_lane]
    other_pressure = sum(counts[l] for l in LANE_ORDER if l != current_lane)

    # More vehicles + longer wait → more time
    # High other-lane pressure → less time (switch sooner)
    raw = (active_count * 1.8) + (active_wait * 0.4) - (other_pressure * 0.6)
    duration = max(MIN_GREEN, min(MAX_GREEN, raw))

    # Ambulance in another lane → cut time short (preemption will happen)
    if any(ambulance[l] for l in LANE_ORDER if l != current_lane):
        duration = min(duration, MIN_GREEN + 2)

    # Empty lane → give minimum
    if active_count == 0:
        duration = MIN_GREEN

    # ── Feature vector (13 values) ───────────────────────────────────────────
    features = []
    for lane in LANE_ORDER:
        features.append(counts[lane] / 10.0)
    for lane in LANE_ORDER:
        features.append(waits[lane] / 30.0)
    for lane in LANE_ORDER:
        features.append(1.0 if ambulance[lane] else 0.0)
    features.append(lane_idx / 3.0)

    # Normalise label to (0, 1) for Sigmoid output
    label = (duration - MIN_GREEN) / (MAX_GREEN - MIN_GREEN)

    return features, label


def build_dataset(n: int):
    X, y = [], []
    for _ in range(n):
        features, label = generate_scenario()
        X.append(features)
        y.append([label])
    return (
        torch.tensor(X, dtype=torch.float32),
        torch.tensor(y, dtype=torch.float32),
    )


def train():
    print(f"[Train] Generating {NUM_SAMPLES:,} synthetic scenarios...")
    X, y = build_dataset(NUM_SAMPLES)
    dataset = TensorDataset(X, y)
    loader  = DataLoader(dataset, batch_size=BATCH_SIZE, shuffle=True)

    model     = SignalDurationNet()
    criterion = nn.MSELoss()
    optimiser = torch.optim.Adam(model.parameters(), lr=LEARNING_RATE)

    print(f"[Train] Starting training — {EPOCHS} epochs, batch={BATCH_SIZE}")
    model.train()

    for epoch in range(1, EPOCHS + 1):
        total_loss = 0.0
        for xb, yb in loader:
            optimiser.zero_grad()
            # Forward: raw sigmoid output for MSE against normalised label
            raw = model.net(xb)
            loss = criterion(raw, yb)
            loss.backward()
            optimiser.step()
            total_loss += loss.item()

        avg_loss = total_loss / len(loader)
        print(f"  Epoch {epoch:02d}/{EPOCHS}  loss={avg_loss:.6f}")

    save_path = os.path.abspath(SAVE_PATH)
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    torch.save(model.state_dict(), save_path)
    print(f"\n[Train] ✅ Model saved → {save_path}")

    # Quick validation
    model.eval()
    sample_x = X[:8]
    with torch.no_grad():
        raw_out  = model.net(sample_x)
        durations = raw_out * (MAX_GREEN - MIN_GREEN) + MIN_GREEN
    print("\n[Train] Sample predictions (should be in [8, 30]):")
    for i, d in enumerate(durations.squeeze().tolist()):
        label_d = y[i].item() * (MAX_GREEN - MIN_GREEN) + MIN_GREEN
        print(f"  Scenario {i+1}: predicted={d:.1f}s  label={label_d:.1f}s")


if __name__ == '__main__':
    train()
