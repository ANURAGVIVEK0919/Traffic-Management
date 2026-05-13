"""
Video Mode Autonomous Runner
Executes video pipeline tests and reports on YOLO inference status.
"""

import subprocess
import os
from datetime import datetime

def run_video_suite():
    print(f"🎬 Starting Video Pipeline Validation | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)
    
    test_file = "tests/test_video_pipeline.py"
    print(f"Running: {test_file}...")
    
    try:
        process = subprocess.run(
            ["python", test_file],
            capture_output=True,
            text=True,
            timeout=180 # Longer timeout for video processing start
        )
        
        if process.returncode == 0:
            print("PASS: Video Pipeline is Operational.")
            print(process.stdout)
        else:
            print("FAIL: Video Pipeline Error.")
            print("-" * 40)
            print(process.stdout)
            print(process.stderr)
            print("-" * 40)
            
    except Exception as e:
        print(f"Fatal Error: {e}")

    print("="*80)

if __name__ == "__main__":
    run_video_suite()
