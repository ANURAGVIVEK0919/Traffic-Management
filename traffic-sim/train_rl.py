"""
train_rl.py - Complete training script for RL traffic signal system

This script:
- Starts the FastAPI backend server
- Runs multiple training episodes using video pipeline
- Accumulates experience in replay buffer across episodes
- Continuously trains the DQN model
- Saves checkpoints and final model
- Tracks and logs training progress
"""

import os
import sys
import time
import threading
import subprocess
import requests
from pathlib import Path
import torch

# Ensure backend is in path
sys.path.insert(0, str(Path(__file__).parent))

from backend.perception.video_pipeline import run_pipeline
from backend.controllers import rl_controller

# Configuration
NUM_EPISODES = 10
VIDEO_PATH = "uploads/video1.mp4"
CONFIG_PATH = "backend/perception/config/junction_demo.json"
BASE_URL = "http://127.0.0.1:8000"
SAMPLE_FPS = 3
CHECKPOINT_DIR = Path("models")
CHECKPOINT_DIR.mkdir(exist_ok=True)

# Server control
SERVER_PORT = 8000
server_process = None
server_ready = False


def start_backend_server():
    """Start FastAPI backend server in subprocess"""
    global server_process, server_ready
    
    print("[SERVER] Starting FastAPI backend...")
    try:
        server_process = subprocess.Popen(
            [
                sys.executable, "-m", "uvicorn",
                "backend.main:app",
                "--host", "127.0.0.1",
                "--port", str(SERVER_PORT),
                "--log-level", "info"
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(Path(__file__).parent)
        )
        
        # Wait for server to be ready
        max_wait = 30
        waited = 0
        while waited < max_wait:
            try:
                response = requests.get(f"{BASE_URL}/docs", timeout=2)
                if response.status_code == 200:
                    print("[SERVER] ✓ Backend server is running")
                    server_ready = True
                    return True
            except requests.ConnectionError:
                time.sleep(0.5)
                waited += 0.5
        
        print("[SERVER] ✗ Server did not start within timeout")
        return False
        
    except Exception as e:
        print(f"[SERVER] ✗ Failed to start server: {e}")
        return False


def stop_backend_server():
    """Stop FastAPI backend server"""
    global server_process
    if server_process:
        print("[SERVER] Stopping FastAPI backend...")
        server_process.terminate()
        try:
            server_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_process.kill()
        print("[SERVER] ✓ Server stopped")


def verify_video_exists():
    """Verify video file exists"""
    if not Path(VIDEO_PATH).exists():
        print(f"[ERROR] Video not found: {VIDEO_PATH}")
        return False
    print(f"[VIDEO] Found: {VIDEO_PATH}")
    return True


def verify_config_exists():
    """Verify config file exists"""
    if not Path(CONFIG_PATH).exists():
        print(f"[ERROR] Config not found: {CONFIG_PATH}")
        return False
    print(f"[CONFIG] Found: {CONFIG_PATH}")
    return True


def get_training_stats():
    """Extract training metrics from RL controller"""
    return {
        'replay_size': len(rl_controller._replay_buffer),
        'epsilon': rl_controller._epsilon,
        'loss': rl_controller._last_loss,
    }


def print_episode_summary(episode_num, stats_before, stats_after):
    """Print episode training summary"""
    print("\n" + "="*70)
    print(f"Episode {episode_num} complete")
    print("="*70)
    print(f"  Replay buffer:    {stats_before['replay_size']:4d} → {stats_after['replay_size']:4d}")
    print(f"  Loss:             {stats_before['loss']:>10.6f} → {stats_after['loss']:>10.6f}")
    print(f"  Epsilon:          {stats_before['epsilon']:>10.6f} → {stats_after['epsilon']:>10.6f}")
    print(f"  Transitions:      +{stats_after['replay_size'] - stats_before['replay_size']}")
    print("="*70 + "\n")


def save_checkpoint(episode_num):
    """Save model checkpoint for specific episode"""
    checkpoint_path = CHECKPOINT_DIR / f"checkpoint_ep_{episode_num:02d}.pth"
    torch.save(rl_controller._q_network.state_dict(), checkpoint_path)
    print(f"[CHECKPOINT] Saved: {checkpoint_path}")
    return checkpoint_path


def save_final_model():
    """Save final trained model"""
    final_path = CHECKPOINT_DIR / "final_dqn_model.pth"
    torch.save(rl_controller._q_network.state_dict(), final_path)
    print(f"[FINAL MODEL] Saved: {final_path}")
    return final_path


def run_training_episode(episode_num):
    """Run single training episode with video pipeline"""
    print(f"\n[EPISODE {episode_num}] Starting...")
    
    stats_before = get_training_stats()
    print(f"[EPISODE {episode_num}] Stats before: "
          f"buffer={stats_before['replay_size']}, "
          f"loss={stats_before['loss']:.6f}, "
          f"epsilon={stats_before['epsilon']:.6f}")
    
    try:
        # Run video pipeline - this makes requests to /rl/decision endpoint
        # which calls handle_rl_decision() and accumulates training data
        print(f"[EPISODE {episode_num}] Running video pipeline...")
        run_pipeline(
            video_path=Path(VIDEO_PATH),
            config_path=Path(CONFIG_PATH),
            base_url=BASE_URL,
            sample_fps=SAMPLE_FPS,
            preview=False,
            output_video=None,
            smooth_alpha=0.6,
            session_id=None,
            select_homography_points=False,
        )
        print(f"[EPISODE {episode_num}] ✓ Video pipeline completed")
        
    except Exception as e:
        print(f"[EPISODE {episode_num}] ✗ Error: {e}")
        raise
    
    stats_after = get_training_stats()
    print_episode_summary(episode_num, stats_before, stats_after)
    
    return stats_before, stats_after


def print_training_header():
    """Print training header"""
    print("\n" + "="*70)
    print("TRAINING STARTED - RL Traffic Signal System")
    print("="*70)
    print(f"  Episodes:         {NUM_EPISODES}")
    print(f"  Video:            {VIDEO_PATH}")
    print(f"  Config:           {CONFIG_PATH}")
    print(f"  Sample FPS:       {SAMPLE_FPS}")
    print(f"  Base URL:         {BASE_URL}")
    print(f"  Checkpoint Dir:   {CHECKPOINT_DIR}")
    print("="*70 + "\n")


def print_final_summary(all_stats):
    """Print final training summary"""
    print("\n" + "="*70)
    print("TRAINING COMPLETED")
    print("="*70)
    
    if all_stats:
        final_stats = all_stats[-1]['after']
        initial_stats = all_stats[0]['before']
        
        print(f"  Initial replay buffer:    {initial_stats['replay_size']}")
        print(f"  Final replay buffer:      {final_stats['replay_size']}")
        print(f"  Total transitions:        {final_stats['replay_size'] - initial_stats['replay_size']}")
        print(f"  Initial loss:             {initial_stats['loss']:.6f}")
        print(f"  Final loss:               {final_stats['loss']:.6f}")
        print(f"  Initial epsilon:          {initial_stats['epsilon']:.6f}")
        print(f"  Final epsilon:            {final_stats['epsilon']:.6f}")
    
    print(f"  Final model:              {CHECKPOINT_DIR / 'final_dqn_model.pth'}")
    print("="*70 + "\n")


def main():
    """Main training orchestration"""
    
    print_training_header()
    
    # Verify prerequisites
    if not verify_video_exists():
        return 1
    if not verify_config_exists():
        return 1
    
    # Start backend server
    if not start_backend_server():
        print("[ERROR] Failed to start backend server")
        return 1
    
    try:
        # Small delay to ensure server is fully ready
        time.sleep(2)
        
        # Run training episodes
        all_stats = []
        for episode in range(1, NUM_EPISODES + 1):
            stats_before, stats_after = run_training_episode(episode)
            all_stats.append({
                'episode': episode,
                'before': stats_before,
                'after': stats_after,
            })
            
            # Save checkpoint every episode
            save_checkpoint(episode)
            
            # Small delay between episodes
            if episode < NUM_EPISODES:
                time.sleep(1)
        
        # Save final model
        final_model_path = save_final_model()
        
        # Print final summary
        print_final_summary(all_stats)
        
        print("[SUCCESS] Training completed successfully")
        print(f"[OUTPUT] Final model: {final_model_path}")
        print(f"[OUTPUT] Checkpoints: {CHECKPOINT_DIR}/checkpoint_ep_*.pth")
        
        return 0
        
    except Exception as e:
        print(f"[ERROR] Training failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    finally:
        stop_backend_server()


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
