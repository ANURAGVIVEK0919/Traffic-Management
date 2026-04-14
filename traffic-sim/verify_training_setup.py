#!/usr/bin/env python3
"""
Verification script for RL Training System
Checks all components are in place and ready to use
"""

import os
import sys
from pathlib import Path

def check_file_exists(path, description):
    """Check if file exists and print status"""
    path_obj = Path(path)
    exists = path_obj.exists()
    status = "✓" if exists else "✗"
    size_info = f" ({path_obj.stat().st_size / 1024:.1f} KB)" if exists else ""
    print(f"  {status} {description:40s} {path}{size_info}")
    return exists

def check_directory_exists(path, description):
    """Check if directory exists"""
    path_obj = Path(path)
    exists = path_obj.is_dir()
    status = "✓" if exists else "✗"
    print(f"  {status} {description:40s} {path}")
    return exists

def check_python_module(module_name, description):
    """Check if Python module is installed"""
    try:
        __import__(module_name)
        print(f"  ✓ {description:40s} (installed)")
        return True
    except ImportError:
        print(f"  ✗ {description:40s} (NOT installed)")
        return False

def main():
    print("\n" + "="*70)
    print("RL TRAINING SYSTEM - VERIFICATION SCRIPT")
    print("="*70)
    
    all_checks_pass = True
    
    # 1. Check training script
    print("\n1. TRAINING SCRIPT")
    print("-" * 70)
    if not check_file_exists("train_rl.py", "Main training script"):
        all_checks_pass = False
    
    # 2. Check documentation
    print("\n2. DOCUMENTATION FILES")
    print("-" * 70)
    docs = [
        ("TRAINING_QUICKSTART.md", "Quick start guide"),
        ("TRAINING_README.md", "Complete reference"),
        ("TRAINING_INTEGRATION.md", "Technical integration guide"),
        ("TRAINING_SUMMARY.md", "Summary and results"),
        ("MODEL_USAGE.md", "Model usage guide"),
        ("INDEX.md", "Complete index"),
    ]
    
    for doc_file, description in docs:
        if not check_file_exists(doc_file, description):
            all_checks_pass = False
    
    # 3. Check trained models
    print("\n3. TRAINED MODELS")
    print("-" * 70)
    
    # Final model
    if not check_file_exists("models/final_dqn_model.pth", "Final trained model"):
        all_checks_pass = False
    
    # Checkpoints
    checkpoint_count = 0
    for i in range(1, 11):
        checkpoint_path = f"models/checkpoint_ep_{i:02d}.pth"
        if Path(checkpoint_path).exists():
            checkpoint_count += 1
    
    print(f"  {'✓' if checkpoint_count == 10 else '✗'} Checkpoints saved             {checkpoint_count}/10")
    if checkpoint_count < 10:
        all_checks_pass = False
    
    # Training logs
    if not check_file_exists("models/rl_logs.csv", "Training logs CSV"):
        all_checks_pass = False
    
    # 4. Check dependencies
    print("\n4. PYTHON DEPENDENCIES")
    print("-" * 70)
    dependencies = [
        ("torch", "PyTorch"),
        ("fastapi", "FastAPI"),
        ("uvicorn", "Uvicorn"),
        ("cv2", "OpenCV"),
        ("numpy", "NumPy"),
        ("requests", "Requests"),
    ]
    
    missing_deps = []
    for module, description in dependencies:
        if not check_python_module(module, description):
            missing_deps.append(description)
            all_checks_pass = False
    
    # 5. Check backend
    print("\n5. BACKEND STRUCTURE")
    print("-" * 70)
    
    backend_checks = [
        ("backend/main.py", "FastAPI app"),
        ("backend/controllers/rl_controller.py", "RL controller"),
        ("backend/perception/video_pipeline.py", "Video pipeline"),
        ("backend/routers/rl.py", "RL router"),
    ]
    
    for file_path, description in backend_checks:
        if not check_file_exists(file_path, description):
            all_checks_pass = False
    
    # 6. Check data
    print("\n6. DATA FILES")
    print("-" * 70)
    
    if not check_file_exists("uploads/video1.mp4", "Training video"):
        all_checks_pass = False
    
    if not check_file_exists("backend/perception/config/junction_demo.json", 
                            "Lane calibration config"):
        all_checks_pass = False
    
    # 7. Check directories
    print("\n7. REQUIRED DIRECTORIES")
    print("-" * 70)
    
    directories = [
        ("models", "Models directory"),
        ("uploads", "Uploads directory"),
        ("backend", "Backend directory"),
    ]
    
    for dir_path, description in directories:
        if not check_directory_exists(dir_path, description):
            all_checks_pass = False
    
    # 8. Summary
    print("\n" + "="*70)
    if all_checks_pass:
        print("✓ ALL CHECKS PASSED - System is ready!")
        print("="*70)
        print("\nNEXT STEPS:")
        print("  1. Read TRAINING_QUICKSTART.md for 5-minute overview")
        print("  2. Run: python train_rl.py")
        print("  3. Wait ~40 minutes for training to complete")
        print("  4. Check models/ directory for output files")
        print("  5. See MODEL_USAGE.md for inference examples")
        return 0
    else:
        print("✗ SOME CHECKS FAILED - Please fix issues above")
        print("="*70)
        
        if missing_deps:
            print("\nMISSING DEPENDENCIES - Install with:")
            print("  pip install " + " ".join([d.lower().replace(" ", "") for d in missing_deps]))
        
        print("\nFor detailed help, see TRAINING_QUICKSTART.md")
        return 1

if __name__ == "__main__":
    sys.exit(main())
