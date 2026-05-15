import subprocess
import time
import webbrowser
import os
import sys
from pathlib import Path

def start_system(scenario_name):
    project_root = Path(__file__).resolve().parents[1]
    
    print(f"🚀 [LAUNCHER] Starting Traffic Management System for Scenario: {scenario_name}")
    
    # Map scenarios to specific video files
    SCENARIO_VIDEOS = {
        "peak_hour": "videos/peak_demo.mp4",
        "emergency_priority": "videos/emergency_demo.mp4",
        "asymmetric_fairness": "videos/asymmetric_demo.mp4",
        "default": "videos/standard_traffic.mp4"
    }
    
    video_path = SCENARIO_VIDEOS.get(scenario_name, SCENARIO_VIDEOS["default"])
    
    # 1. Start Backend in a new window
    print("📡 Starting Backend Server...")
    backend_cmd = f'powershell -NoExit -Command "cd \'{project_root}\'; .\\venv\\Scripts\\activate; python -m backend.main"'
    subprocess.Popen(['start', 'powershell', '-NoExit', '-Command', backend_cmd], shell=True)
    
    # 2. Wait for backend to warm up
    time.sleep(5)
    
    # 3. Start Video Pipeline for the scenario
    # We use a session_id that the frontend will also use
    session_id = f"demo_{scenario_name}"
    print(f"🎥 Starting Video Pipeline for {scenario_name}...")
    pipeline_cmd = f'powershell -NoExit -Command "cd \'{project_root}\'; .\\venv\\Scripts\\activate; python -m backend.ai.perception.video_pipeline --video {video_path} --session-id {session_id} --base-url http://localhost:8000"'
    subprocess.Popen(['start', 'powershell', '-NoExit', '-Command', pipeline_cmd], shell=True)
    
    # 4. Start Frontend in a new window
    print("🎨 Starting Frontend Dashboard...")
    frontend_dir = project_root / "frontend"
    frontend_cmd = f'powershell -NoExit -Command "cd \'{frontend_dir}\'; npm start"'
    subprocess.Popen(['start', 'powershell', '-NoExit', '-Command', frontend_cmd], shell=True)
    
    # 5. Wait for frontend to warm up
    time.sleep(10)
    
    # 6. Open Browser to the Simulation Page
    url = f"http://localhost:3000/simulation?mode=video&session_id={session_id}&scenario={scenario_name}"
    print(f"🌐 Opening Dashboard: {url}")
    webbrowser.open(url)
    
    # 6. Optional: Trigger the video pipeline if it's a video-based scenario
    # (For demonstration, we might want to run a specific demo script too)
    print("\n✅ System is now running! Check the new terminal windows.")
    print("Press Ctrl+C in this terminal to stop tracking (Servers will remain open).")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        start_system(sys.argv[1])
    else:
        start_system("default")
