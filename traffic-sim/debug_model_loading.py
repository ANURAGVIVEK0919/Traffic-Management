#!/usr/bin/env python
"""
Debug script to verify RL model loading end-to-end.

This script:
1. Checks if model file exists
2. Lists all .pth files in models/
3. Verifies model can be loaded
4. Checks model architecture
5. Tests inference mode setup

Run: python debug_model_loading.py
"""

import os
import sys
from pathlib import Path

print("\n" + "="*70)
print("RL MODEL LOADING VERIFICATION")
print("="*70 + "\n")

# Step 1: Check if models directory exists
print("[STEP 1] Checking models directory...")
if not os.path.exists("models"):
    print("  ✗ ERROR: models/ directory does not exist!")
    sys.exit(1)
print("  ✓ models/ directory exists")

# Step 2: List all .pth files
print("\n[STEP 2] Listing available .pth files...")
pth_files = [f for f in os.listdir("models") if f.endswith('.pth')]
if not pth_files:
    print("  ✗ ERROR: No .pth files found in models/")
    sys.exit(1)

print(f"  ✓ Found {len(pth_files)} model file(s):")
for f in sorted(pth_files):
    path = os.path.join("models", f)
    size_kb = os.path.getsize(path) / 1024
    print(f"    - {f} ({size_kb:.1f} KB)")

# Step 3: Check for the expected trained model
print("\n[STEP 3] Checking for trained model...")
MODEL_PATH = "models/final_dqn_model.pth"
if not os.path.exists(MODEL_PATH):
    print(f"  ✗ ERROR: Expected model not found at {MODEL_PATH}")
    print("\n  Available models:")
    for f in sorted(pth_files):
        print(f"    - {f}")
    sys.exit(1)
print(f"  ✓ Trained model found: {MODEL_PATH}")
size_kb = os.path.getsize(MODEL_PATH) / 1024
print(f"    Size: {size_kb:.1f} KB")

# Step 4: Try to load the model
print("\n[STEP 4] Loading model...")
try:
    import torch
    print("  ✓ PyTorch imported")
    
    state_dict = torch.load(MODEL_PATH, map_location='cpu')
    print("  ✓ State dict loaded from disk")
    
    print(f"  ✓ State dict keys: {len(state_dict)} entries")
    for key in list(state_dict.keys())[:3]:
        print(f"    - {key}: {state_dict[key].shape}")
    
except Exception as e:
    print(f"  ✗ ERROR: Failed to load model: {e}")
    sys.exit(1)

# Step 5: Check model architecture
print("\n[STEP 5] Checking model architecture...")
try:
    from backend.controllers.rl_controller import SignalDQN, STATE_SIZE, ACTION_SIZE
    print(f"  ✓ SignalDQN class imported")
    print(f"  ✓ Architecture: {STATE_SIZE} inputs → 64 hidden → {ACTION_SIZE} actions")
    
    model = SignalDQN()
    print(f"  ✓ Fresh model created")
    
    model.load_state_dict(state_dict)
    print(f"  ✓ State dict loaded into model")
    
except Exception as e:
    print(f"  ✗ ERROR: Architecture check failed: {e}")
    sys.exit(1)

# Step 6: Test inference mode
print("\n[STEP 6] Testing inference mode...")
try:
    model.eval()
    print(f"  ✓ Model set to eval mode")
    
    import torch
    test_input = torch.randn(1, STATE_SIZE)
    with torch.no_grad():
        output = model(test_input)
    print(f"  ✓ Test inference successful")
    print(f"    Input shape: {test_input.shape}")
    print(f"    Output shape: {output.shape}")
    print(f"    Output values: {output.squeeze().tolist()}")
    
except Exception as e:
    print(f"  ✗ ERROR: Inference test failed: {e}")
    sys.exit(1)

# Step 7: Check controller integration
print("\n[STEP 7] Checking controller integration...")
try:
    from backend.controllers import rl_controller
    print(f"  ✓ RL controller imported")
    print(f"  ✓ MODEL_PATH in controller: {rl_controller.MODEL_PATH}")
    print(f"  ✓ INFERENCE_MODE: {rl_controller.INFERENCE_MODE}")
    print(f"  ✓ Model training status: {rl_controller._q_network.training}")
    
except Exception as e:
    print(f"  ✗ ERROR: Controller check failed: {e}")
    sys.exit(1)

# Final summary
print("\n" + "="*70)
print("✓ ALL CHECKS PASSED")
print("="*70)
print("\nModel loading is working correctly!")
print("\nTo use the model:")
print("  1. Set INFERENCE_MODE = True in rl_controller.py")
print("  2. Model will be loaded automatically on next import")
print("  3. Run test_rl_model.py to evaluate performance")
print("\n" + "="*70 + "\n")
