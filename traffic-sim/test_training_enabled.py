#!/usr/bin/env python
"""Quick test to verify training mode is enabled."""
from backend.controllers.rl_controller import (
    handle_rl_decision,
    INFERENCE_MODE,
    MIN_REPLAY_SIZE,
    _replay_buffer,
    _epsilon,
    _last_loss,
)

print("=" * 50)
print("TRAINING MODE CHECK")
print("=" * 50)
print(f"INFERENCE_MODE: {INFERENCE_MODE}")
print(f"MIN_REPLAY_SIZE: {MIN_REPLAY_SIZE}")
print()

# Simulate 110 decision cycles to exceed MIN_REPLAY_SIZE
seq = [
    {"north": 10, "south": 5, "east": 8, "west": 2},
    {"north": 8, "south": 4, "east": 7, "west": 3},
    {"north": 9, "south": 6, "east": 8, "west": 2},
    {"north": 10, "south": 5, "east": 9, "west": 3},
    {"north": 7, "south": 3, "east": 6, "west": 2},
]

print("Running 110 steps to test replay buffer filling and training...")
for i in range(110):
    d = seq[i % len(seq)]
    req = {
        "line_counts": d,
        "wait_time_by_direction": d,
        "queue_length_by_direction": d,
        "lane_state": {"north": 0, "south": 0, "east": 0, "west": 0},
        "timestamp": i,
    }
    out = handle_rl_decision(req)
    debug = out.get("debug", {})

    if i in [0, 49, 99, 109]:
        print(f"\nStep {i+1}:")
        print(f"  Replay Size: {debug.get('replay_size', 'N/A')}")
        print(f"  Loss: {debug.get('loss', 'N/A')}")
        print(f"  Epsilon: {debug.get('epsilon', 'N/A'):.4f}")
        print(f"  Action: {debug.get('action_meaning', 'N/A')}")

print("\n" + "=" * 50)
print("EXPECTED RESULTS:")
print("✓ Replay Size: 0 → increases → 100+ after step 100")
print("✓ Loss: 0.0 → becomes non-zero after buffer fills")
print("✓ Epsilon: 1.0 → decreases gradually")
print("✓ Actions: Random initially (< 3000 steps)")
print("=" * 50)
