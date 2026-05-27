import requests
import time
import sys
from pathlib import Path

BASE = "http://localhost:8000"
VIDEO_PATH = Path(r"e:\Traffic Managment\Traffic-Management\traffic-sim\uploads\WhatsApp Video 2026-04-15 at 5.07.17 PM.mp4")

print("=======================================================")
print("  STEP 1: Backend Health")
print("=======================================================")
try:
    r = requests.get(f"{BASE}/docs", timeout=5)
    print("✅ Backend reachable" if r.status_code == 200 else f"❌ Backend reachable -> {r.status_code}")
except Exception as e:
    print(f"❌ Backend not running! Error: {e}")
    sys.exit(1)

print("\n=======================================================")
print("  STEP 2: Video Upload")
print("=======================================================")
if not VIDEO_PATH.exists():
    print(f"❌ Video not found at {VIDEO_PATH}")
    sys.exit(1)

print("📤 Uploading video...")
try:
    with open(VIDEO_PATH, "rb") as f:
        r = requests.post(f"{BASE}/upload/video",
                         files={"video": (VIDEO_PATH.name, f, "video/mp4")},
                         timeout=120)
    if r.status_code != 200:
        print(f"❌ Upload failed: {r.text[:200]}")
        sys.exit(1)
    
    upload_data = r.json()
    session_id = upload_data.get("session_id")
    video_path = upload_data.get("video_path")
    print(f"✅ Upload successful. Session ID: {session_id}")
except Exception as e:
    print(f"❌ Upload error: {e}")
    sys.exit(1)

print("\n=======================================================")
print("  STEP 3: Start Processing Job")
print("=======================================================")
try:
    r = requests.post(f"{BASE}/jobs/start",
                     json={"session_id": session_id, "video_path": video_path},
                     timeout=15)
    if r.status_code != 200:
        print(f"❌ Job start failed: {r.text[:200]}")
        sys.exit(1)
    print(f"✅ Job started.")
except Exception as e:
    print(f"❌ Job start error: {e}")
    sys.exit(1)

print("\n=======================================================")
print("  STEP 4: Monitoring Progress")
print("=======================================================")
print("⏳ Processing video... (This takes a few minutes depending on hardware)")

last_progress = -1
poll_errors = 0
start_time = time.time()
completed = False

while not completed:
    time.sleep(2)
    try:
        r = requests.get(f"{BASE}/jobs/{session_id}/status", timeout=5)
        if r.status_code != 200:
            poll_errors += 1
            if poll_errors > 5:
                print("❌ Too many 404s — stopping")
                sys.exit(1)
            continue
            
        poll_errors = 0
        status_data = r.json()
        status = status_data.get("status", "unknown")
        progress = int(status_data.get("progress", 0) or 0)
        elapsed = int(time.time() - start_time)
        
        if progress != last_progress:
            bar = "█" * (progress // 5) + "░" * (20 - progress // 5)
            print(f"  [{bar}] {progress:3d}% | {status:10s} | {elapsed:3d}s elapsed", end="\r")
            last_progress = progress
            
        if status == "completed":
            completed = True
            print(f"\n\n✅ Pipeline complete in {elapsed}s!")
            break
        elif status == "failed":
            err = status_data.get("error_message", "unknown")
            print(f"\n\n❌ Job FAILED: {err}")
            sys.exit(1)
            
    except Exception as e:
        poll_errors += 1

print("\n=======================================================")
print("  STEP 5: Final Results (AI vs Static)")
print("=======================================================")
try:
    r = requests.get(f"{BASE}/simulation/results/{session_id}", timeout=15)
    if r.status_code == 200:
        results = r.json()
        dynamic = results.get("dynamic", {})
        static  = results.get("static",  {})

        print(f"\n  {'Metric':<30} {'AI (Dynamic)':>14} {'Static':>14} {'Winner':>10}")
        print(f"  {'─'*70}")

        metrics = [
            ("avg_wait_time",           "Avg Wait Time (s)",     True),
            ("total_vehicles_crossed",  "Total Crossed",          False),
            ("co2_estimate",            "CO2 Estimate (g)",       True),
            ("avg_green_utilization",   "Green Utilization (%)",  False),
        ]

        for key, label, lower_is_better in metrics:
            d_val = float(dynamic.get(key, 0) or 0)
            s_val = float(static.get(key, 0) or 0)
            
            winner = ""
            if d_val != s_val:
                if lower_is_better:
                    winner = "AI" if d_val < s_val else "Static"
                else:
                    winner = "AI" if d_val > s_val else "Static"
            else:
                winner = "Tie"
                
            print(f"  {label:<30} {d_val:>14.1f} {s_val:>14.1f} {winner:>10}")
            
    else:
        print(f"❌ Results endpoint failed: {r.status_code}")
except Exception as e:
    print(f"❌ Results fetch error: {e}")
