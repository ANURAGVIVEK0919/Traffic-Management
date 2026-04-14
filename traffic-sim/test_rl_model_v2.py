#!/usr/bin/env python
"""
test_rl_model_v2.py - Simplified RL model evaluation

Gets metrics from API after pipeline execution completes.
"""

import os
import sys
import time
import json
import re
import subprocess
import requests
from pathlib import Path
from collections import defaultdict

# Configuration
VIDEO_PATH = Path("uploads/video1.mp4")
CONFIG_PATH = Path("backend/perception/config/junction_demo.json")
BASE_URL = "http://127.0.0.1:8000"
MODEL_PATH = Path("models/final_dqn_model.pth")
SAMPLE_FPS = 2

def start_backend_server():
    """Start FastAPI backend server"""
    print("[SERVER] Starting backend...")
    try:
        server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn",
             "backend.main:app",
             "--host", "127.0.0.1",
             "--port", "8000",
             "--log-level", "error"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Wait for server
        max_wait = 30
        waited = 0
        while waited < max_wait:
            try:
                response = requests.get(f"{BASE_URL}/docs", timeout=2)
                if response.status_code == 200:
                    print("[SERVER] ✓ Backend ready")
                    return server
            except:
                time.sleep(0.5)
                waited += 0.5
        
        print("[SERVER] ✗ Server timeout")
        return None
    except Exception as e:
        print(f"[SERVER] ✗ Failed to start: {e}")
        return None

def stop_backend_server(server):
    """Stop backend server"""
    if server:
        print("[SERVER] Stopping backend...")
        server.terminate()
        try:
            server.wait(timeout=5)
        except:
            server.kill()
        print("[SERVER] Stopped")

def load_trained_model():
    """Load trained DQN model"""
    print("[MODEL] Loading trained model...")
    sys.path.insert(0, str(Path(__file__).parent))
    
    if not MODEL_PATH.exists():
        print(f"[ERROR] Model not found at {MODEL_PATH}")
        return False
    
    try:
        import torch
        from backend.controllers import rl_controller
        
        state_dict = torch.load(MODEL_PATH, map_location='cpu')
        rl_controller._q_network.load_state_dict(state_dict)
        rl_controller.INFERENCE_MODE = True
        rl_controller._epsilon = 0.05
        rl_controller._q_network.eval()
        print(f"[MODEL] ✓ Model loaded successfully")
        return True
    except Exception as e:
        print(f"[MODEL] ✗ Failed to load: {e}")
        return False

def run_pipeline_and_capture_session_id(mode='rl'):
    """Run pipeline and extract session ID from output"""
    print(f"\n[{mode.upper()}] Running video pipeline...")
    
    try:
        # Import here to use the loaded model
        sys.path.insert(0, str(Path(__file__).parent))
        from backend.perception.video_pipeline import run_pipeline
        from backend.controllers import rl_controller
        
        # Set mode
        if mode == 'rl':
            rl_controller.INFERENCE_MODE = True
            rl_controller._epsilon = 0.05
        else:
            rl_controller.INFERENCE_MODE = False
            rl_controller._epsilon = 0.95  # Mostly random
        
        # Capture output
        from io import StringIO
        import contextlib
        
        output = StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            run_pipeline(
                video_path=VIDEO_PATH,
                config_path=CONFIG_PATH,
                base_url=BASE_URL,
                sample_fps=SAMPLE_FPS,
                preview=False,
                output_video=None,
                smooth_alpha=0.6,
                session_id=None,
                select_homography_points=False
            )
        
        # Extract session ID from output
        output_text = output.getvalue()
        match = re.search(r'session\s+([a-f0-9-]{36})', output_text, re.IGNORECASE)
        if match:
            session_id = match.group(1)
            print(f"[{mode.upper()}] ✓ Pipeline completed (session: {session_id[:8]}...)")
            return session_id
        else:
            print(f"[{mode.upper()}] ✓ Pipeline completed (no session ID found)")
            return None
            
    except Exception as e:
        print(f"[{mode.upper()}] ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return None

def get_decisions_from_api(session_id):
    """Fetch decisions from API"""
    if not session_id:
        return []
    
    try:
        response = requests.get(
            f"{BASE_URL}/simulation/decision-log/{session_id}",
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, dict) and 'events' in data:
                return data['events']
            elif isinstance(data, list):
                return data
        return []
    except Exception as e:
        print(f"[API] Error retrieving decisions: {e}")
        return []

def extract_metrics(decisions):
    """Extract metrics from decision events"""
    metrics = {
        'wait_times': defaultdict(list),
        'queue_lengths': defaultdict(list),
        'frames_processed': 0,
        'total_wait_time': 0.0,
        'max_queue_length': 0,
    }
    
    for event in decisions:
        if event.get('eventType') != 'rl_decision':
            continue
        
        payload = event.get('payload', {})
        decision = payload.get('decision', {})
        debug = decision.get('debug', {})
        
        metrics['frames_processed'] += 1
        
        # Extract wait times
        waits = debug.get('wait_time_by_direction', {})
        for direction, wait in waits.items():
            if isinstance(wait, (int, float)):
                metrics['wait_times'][direction].append(wait)
                metrics['total_wait_time'] += wait
        
        # Extract queues
        queues = debug.get('queue_length_by_direction', {})
        for direction, queue in queues.items():
            if isinstance(queue, (int, float)):
                metrics['queue_lengths'][direction].append(queue)
                max_q = max((v for v in queues.values() if isinstance(v, (int, float))), default=0)
                if max_q > metrics['max_queue_length']:
                    metrics['max_queue_length'] = max_q
    
    return metrics

def compute_averages(metrics):
    """Compute average metrics"""
    results = {
        'overall_avg_wait': 0.0,
        'max_queue_length': metrics['max_queue_length'],
        'frames_processed': metrics['frames_processed'],
        'by_direction': {'wait': {}, 'queue': {}}
    }
    
    for direction in ['north', 'south', 'east', 'west']:
        waits = metrics['wait_times'].get(direction, [])
        queues = metrics['queue_lengths'].get(direction, [])
        
        results['by_direction']['wait'][direction] = sum(waits) / len(waits) if waits else 0
        results['by_direction']['queue'][direction] = sum(queues) / len(queues) if queues else 0
    
    if metrics['frames_processed'] > 0:
        results['overall_avg_wait'] = metrics['total_wait_time'] / metrics['frames_processed']
    
    return results

def print_results(rl_res, static_res):
    """Print formatted comparison"""
    print("\n" + "="*70)
    print("TEST RESULTS - RL vs STATIC BASELINE")
    print("="*70)
    
    print("\n┌─ RL MODEL RESULTS ─────────────────────────────────────────┐")
    print(f"│ Overall Avg Wait:              {rl_res['overall_avg_wait']:.2f} sec")
    print(f"│ Max Queue:                     {rl_res['max_queue_length']} veh")
    print(f"│ Frames:                        {rl_res['frames_processed']}")
    print("└─────────────────────────────────────────────────────────────┘")
    
    print("\n┌─ STATIC BASELINE RESULTS ──────────────────────────────────┐")
    print(f"│ Overall Avg Wait:              {static_res['overall_avg_wait']:.2f} sec")
    print(f"│ Max Queue:                     {static_res['max_queue_length']} veh")
    print(f"│ Frames:                        {static_res['frames_processed']}")
    print("└─────────────────────────────────────────────────────────────┘")
    
    if static_res['overall_avg_wait'] > 0:
        wait_imp = ((static_res['overall_avg_wait'] - rl_res['overall_avg_wait']) / 
                   static_res['overall_avg_wait'] * 100)
    else:
        wait_imp = 0
    
    print("\n┌─ IMPROVEMENT ─────────────────────────────────────────────┐")
    symbol = "✓" if wait_imp > 0 else "✗"
    print(f"│ Wait Time: {symbol} {wait_imp:+.1f}%")
    print(f"│ Frames Processed: {rl_res['frames_processed']}")
    print("└─────────────────────────────────────────────────────────────┘")

def main():
    print("\n" + "="*70)
    print("RL TRAFFIC SIGNAL - EVALUATION TEST")
    print("="*70 + "\n")
    
    if not load_trained_model():
        return
    
    server = start_backend_server()
    if not server:
        return
    
    time.sleep(1)
    
    try:
        # Run RL test
        rl_session = run_pipeline_and_capture_session_id('rl')
        time.sleep(2)
        
        if rl_session:
            rl_decisions = get_decisions_from_api(rl_session)
            rl_metrics = extract_metrics(rl_decisions)
            rl_results = compute_averages(rl_metrics)
            print(f"[RESULTS] RL: {rl_metrics['frames_processed']} frames, {rl_results['overall_avg_wait']:.1f}s avg wait")
        else:
            rl_results = {'overall_avg_wait': 0, 'max_queue_length': 0, 'frames_processed': 0, 'by_direction': {'wait': {}, 'queue': {}}}
        
        # Run static test
        static_session = run_pipeline_and_capture_session_id('static')
        time.sleep(2)
        
        if static_session:
            static_decisions = get_decisions_from_api(static_session)
            static_metrics = extract_metrics(static_decisions)
            static_results = compute_averages(static_metrics)
            print(f"[RESULTS] Static: {static_metrics['frames_processed']} frames, {static_results['overall_avg_wait']:.1f}s avg wait")
        else:
            static_results = {'overall_avg_wait': 0, 'max_queue_length': 0, 'frames_processed': 0, 'by_direction': {'wait': {}, 'queue': {}}}
        
        # Print comparison
        print_results(rl_results, static_results)
        
        # Save results
        results = {
            'rl': rl_results,
            'static': static_results,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'rl_session_id': rl_session,
            'static_session_id': static_session,
        }
        
        with open('models/test_results.json', 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\n[SAVE] Results saved to models/test_results.json")
        
        print("\n✓ Test completed successfully")
        
    finally:
        stop_backend_server(server)

if __name__ == "__main__":
    main()
