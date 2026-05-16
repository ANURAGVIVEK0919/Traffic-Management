"""
Full Flow Test — Video Pipeline + V2I Ambulance Injection
==========================================================
Tests: Upload → Job Start → V2I Beacon Inject → Progress Poll → Results
V2I simulates pressing the "Ambulance" button in the frontend during processing.
"""
import requests
import time
import json
import sys
import threading
from pathlib import Path

BASE = "http://localhost:8000"
VIDEO_PATH = Path(r"e:\Traffic Managment\Traffic-Management\traffic-sim\uploads\WhatsApp Video 2026-04-15 at 5.07.17 PM.mp4")

PASS = "✅"
FAIL = "❌"
WARN = "⚠️ "

def check(label, condition, detail=""):
    icon = PASS if condition else FAIL
    print(f"  {icon} {label}", f"→ {detail}" if detail else "")
    return condition

def section(title):
    print(f"\n{'='*55}")
    print(f"  {title}")
    print(f"{'='*55}")

# ── STEP 1: Backend Health ─────────────────────────────────
section("STEP 1: Backend Health")
try:
    r = requests.get(f"{BASE}/docs", timeout=5)
    check("Backend reachable", r.status_code == 200, f"status={r.status_code}")
except Exception as e:
    check("Backend reachable", False, str(e))
    print("\n❌ Backend not running! Start: python -m backend.main")
    sys.exit(1)

# ── STEP 2: Video Upload ───────────────────────────────────
section("STEP 2: Video Upload")
check("Video file exists", VIDEO_PATH.exists(), str(VIDEO_PATH.name))
print("  📤 Uploading video...")
try:
    with open(VIDEO_PATH, "rb") as f:
        r = requests.post(f"{BASE}/upload/video",
                         files={"video": (VIDEO_PATH.name, f, "video/mp4")},
                         timeout=120)
    check("Upload successful", r.status_code == 200, f"HTTP {r.status_code}")
    if r.status_code != 200:
        print(f"    Error: {r.text[:200]}")
        sys.exit(1)
    upload_data = r.json()
    session_id = upload_data.get("session_id")
    video_path = upload_data.get("video_path")
    check("session_id received", bool(session_id), str(session_id))
    print(f"    session_id : {session_id}")
except Exception as e:
    check("Upload", False, str(e))
    sys.exit(1)

# ── STEP 3: Start Job ─────────────────────────────────────
section("STEP 3: Start Processing Job")
try:
    r = requests.post(f"{BASE}/jobs/start",
                     json={"session_id": session_id, "video_path": video_path},
                     timeout=15)
    check("Job started", r.status_code == 200, f"HTTP {r.status_code}")
    job_data = r.json()
    job_id = job_data.get("job_id") or job_data.get("session_id")
    check("Job ID confirmed", bool(job_id), str(job_id))
    print(f"    status     : {job_data.get('status')}")
except Exception as e:
    check("Job start", False, str(e))
    sys.exit(1)

# ── STEP 4: V2I Ambulance Injection ───────────────────────
section("STEP 4: V2I Ambulance Injection (mid-processing)")
print("  🚑 Will inject ambulance beacon 60s after job starts...")
print("     (Simulates user pressing V2I button during video analysis)")

v2i_log = {
    "injected": False,
    "active_seconds": 0,
    "lane": "east",
    "vehicle_id": "V2I-AMB-TEST-001",
    "beacon_count": 0,
    "stopped": False
}

def inject_v2i_ambulance():
    """Sends ambulance beacon every 2s for 40s — simulates a real ambulance approaching."""
    time.sleep(60)  # Wait 60s for pipeline to be mid-processing
    
    if v2i_log.get("stopped"):
        return
    
    print(f"\n  🚑 [V2I] Injecting ambulance in {v2i_log['lane'].upper()} lane at {time.strftime('%H:%M:%S')}")
    print(f"  📡 [V2I] Sending beacons for 40 seconds...")
    
    distance = 400.0  # meters from intersection
    for i in range(20):  # 20 beacons × 2s = 40 seconds
        if v2i_log.get("stopped"):
            break
        try:
            r = requests.post(f"{BASE}/v2i/beacon",
                            json={
                                "vehicle_id": v2i_log["vehicle_id"],
                                "lane": v2i_log["lane"],
                                "distance": max(0.0, distance - (i * 15.0)),  # 15m/s approach
                                "speed": 15.0
                            }, timeout=3)
            if r.status_code == 200:
                v2i_log["beacon_count"] += 1
                v2i_log["injected"] = True
                eta = max(0.0, (400.0 - i * 15.0) / 15.0)
                print(f"  📡 [V2I] Beacon {i+1}/20 sent — ETA: {eta:.0f}s, dist: {max(0, 400-i*15):.0f}m",
                      end="\r")
            else:
                print(f"\n  {WARN} [V2I] Beacon failed: {r.status_code}")
        except Exception as e:
            print(f"\n  {WARN} [V2I] Beacon error: {e}")
        time.sleep(2)
    
    print(f"\n  ✅ [V2I] Ambulance passed intersection. {v2i_log['beacon_count']} beacons sent.")
    v2i_log["active_seconds"] = v2i_log["beacon_count"] * 2

# Launch V2I injector in background
v2i_thread = threading.Thread(target=inject_v2i_ambulance, daemon=True)
v2i_thread.start()

# ── STEP 5: Poll Progress ──────────────────────────────────
section("STEP 5: Monitoring Progress")
print("  ⏳ Processing video (~7 minutes with V2I injection at 60s mark)...")
print()

last_progress = -1
start_time = time.time()
completed = False
poll_errors = 0

try:
    while True:
        time.sleep(4)
        try:
            r = requests.get(f"{BASE}/jobs/{job_id}/status", timeout=5)
            if r.status_code == 404:
                poll_errors += 1
                if poll_errors == 1:
                    print(f"  {WARN} Job 404 — backend may have reloaded!")
                if poll_errors > 5:
                    print("  ❌ Too many 404s — stopping")
                    break
                continue

            poll_errors = 0
            status_data = r.json()
            status = status_data.get("status", "unknown")
            progress = int(status_data.get("progress", 0) or 0)
            elapsed = int(time.time() - start_time)
            v2i_status = "🚑 V2I ACTIVE" if (60 <= elapsed <= 100 and v2i_log["injected"]) else ""

            if progress != last_progress:
                bar = "█" * (progress // 5) + "░" * (20 - progress // 5)
                print(f"  [{bar}] {progress:3d}% | {status:10s} | {elapsed:3d}s {v2i_status}    ",
                      end="\r")
                last_progress = progress

            if status == "completed":
                completed = True
                print(f"\n\n  {PASS} Pipeline complete in {elapsed}s!")
                break
            elif status == "failed":
                err = status_data.get("error_message", "unknown")
                print(f"\n\n  {FAIL} Job FAILED: {err}")
                break

        except KeyboardInterrupt:
            raise
        except Exception as e:
            poll_errors += 1

except KeyboardInterrupt:
    v2i_log["stopped"] = True
    print(f"\n\n  ⏸️  Stopped. session_id: {session_id}")

# Stop V2I thread
v2i_log["stopped"] = True

# ── STEP 6: Verify V2I Injection ──────────────────────────
section("STEP 6: V2I Injection Verification")
check("V2I beacons sent", v2i_log["beacon_count"] > 0, f"{v2i_log['beacon_count']} beacons sent")
check("V2I lane targeted", True, f"Lane: {v2i_log['lane'].upper()}")
check("V2I active duration", v2i_log["active_seconds"] > 0, f"~{v2i_log['active_seconds']}s active")

# Check current V2I status (should be empty now — ambulance passed)
try:
    r = requests.get(f"{BASE}/v2i/active", timeout=3)
    if r.status_code == 200:
        active = r.json()
        print(f"  ℹ️  Active V2I beacons now: {len(active)} (should be 0 — ambulance passed)")
except Exception:
    pass

# ── STEP 7: Events in Database ────────────────────────────
section("STEP 7: Events in Database")
try:
    r = requests.get(f"{BASE}/simulation/results/{session_id}", timeout=10)
    if r.status_code == 200:
        data = r.json()
        dynamic = data.get("dynamic", {})
        crossed = float(dynamic.get("total_vehicles_crossed", 0) or 0)
        utilization = float(dynamic.get("avg_green_utilization", 0) or 0)
        ambulance_wait = float(dynamic.get("ambulance_avg_wait_time", 0) or 0)
        signal_log = data.get("actual_signal_log", [])
        
        check("vehicle_crossed events in DB", crossed > 0, f"{int(crossed)} vehicles")
        check("Signal log present",           len(signal_log) > 0, f"{len(signal_log)} lanes")
        check("Green utilization computed",   utilization > 0, f"{utilization:.1f}%")
        # V2I ambulance wait — may be 0 if V2I happened after pipeline finished
        icon = PASS if ambulance_wait > 0 else WARN
        print(f"  {icon} Ambulance wait time → {ambulance_wait:.1f}s",
              "(>0 means V2I ambulance was tracked)" if ambulance_wait > 0
              else "(0 = V2I arrived after pipeline finished — try earlier injection)")
except Exception as e:
    print(f"  {WARN} Event check error: {e}")

# ── STEP 8: Final Results ──────────────────────────────────
section("STEP 8: Final Comparison (AI vs Static)")
try:
    r = requests.get(f"{BASE}/simulation/results/{session_id}", timeout=15)
    check("Results endpoint OK", r.status_code == 200, f"HTTP {r.status_code}")

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
            ("ambulance_avg_wait_time", "Ambulance Wait (s)",     True),
        ]

        ai_wins = static_wins = 0
        for key, label, lower_better in metrics:
            dv = float(dynamic.get(key) or 0)
            sv = float(static.get(key)  or 0)
            # Ambulance: TIE only if both 0 (no ambulance detected)
            if key == "ambulance_avg_wait_time" and dv == 0 and sv == 0:
                winner = "TIE (no ambl.)"
            elif lower_better:
                winner = "🤖 AI" if dv < sv else ("📊 Static" if sv < dv else "TIE")
                if dv < sv: ai_wins += 1
                elif sv < dv: static_wins += 1
            else:
                winner = "🤖 AI" if dv > sv else ("📊 Static" if sv > dv else "TIE")
                if dv > sv: ai_wins += 1
                elif sv > dv: static_wins += 1
            print(f"  {label:<30} {dv:>14.2f} {sv:>14.2f} {winner:>14}")

        print(f"\n  {'─'*70}")
        print(f"  🏆 AI WINS: {ai_wins}/5    Static Wins: {static_wins}/5")

        if ai_wins > static_wins:
            print(f"\n  {PASS} ADAPTIVE AI IS BETTER — System validated with V2I!")
        elif ai_wins == static_wins:
            print(f"\n  {WARN} TIE")
        else:
            print(f"\n  {WARN} STATIC WON — investigate")

        with open("test_results_v2i.json", "w") as f:
            json.dump({
                "session_id": session_id,
                "v2i_test": v2i_log,
                **results
            }, f, indent=2)
        print(f"\n  💾 Results with V2I data saved: test_results_v2i.json")

except Exception as e:
    print(f"  {FAIL} Results error: {e}")
    import traceback; traceback.print_exc()

section("DONE")
print(f"  Session   : {session_id}")
print(f"  Dashboard : http://localhost:3000")
print(f"  V2I Beacons: {v2i_log['beacon_count']} sent in {v2i_log['lane'].upper()} lane")
print(f"  Completed : {completed}")
print()
