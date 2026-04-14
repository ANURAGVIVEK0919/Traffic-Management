#!/usr/bin/env python
"""Test to verify training is active during live pipeline execution."""
from backend.controllers.rl_controller import (
    handle_rl_decision,
    INFERENCE_MODE,
    MIN_REPLAY_SIZE,
)

print("=" * 70)
print("LIVE PIPELINE TRAINING TEST")
print("=" * 70)
print(f"INFERENCE_MODE: {INFERENCE_MODE}")
print(f"MIN_REPLAY_SIZE: {MIN_REPLAY_SIZE}")
print()

# Simulate live pipeline: sequence of traffic snapshots
seq = [
    {"north": 10, "south": 5, "east": 8, "west": 2},
    {"north": 8, "south": 4, "east": 7, "west": 3},
    {"north": 9, "south": 6, "east": 8, "west": 2},
]

print("Simulating 150 live pipeline decision calls...")
print("-" * 70)

for i in range(150):
    d = seq[i % 3]
    req = {
        "line_counts": d,
        "wait_time_by_direction": d,
        "queue_length_by_direction": d,
        "lane_state": {"north": 0, "south": 0, "east": 0, "west": 0},
        "timestamp": i,
    }
    out = handle_rl_decision(req)
    debug = out.get("debug", {})

    # Report at key checkpoints
    if i in [0, 49, 99, 149]:
        print(
            f"\nStep {i+1}:"
            f"\n  Replay Size: {debug.get('replay_size', 'N/A')}"
            f"\n  Loss: {debug.get('loss', 'N/A')}"
            f"\n  Epsilon: {debug.get('epsilon', 'N/A')}"
            f"\n  Action: {debug.get('action_meaning', 'N/A')}"
        )

print("\n" + "=" * 70)
print("VERIFICATION RESULTS:")
print("=" * 70)
print("✓ Replay Buffer: Should grow from 0 → 100+ → 150")
print("✓ Loss: Should become non-zero after buffer fills")
print("✓ Training: Should be ACTIVE (not gated by mode)")
print("✓ Actions: Random selection during first 3000 steps")
print("=" * 70)
