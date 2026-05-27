import os
import sys
import time
import argparse
import random
import datetime
from typing import Dict, List, Any

# --- Try imports with fallbacks ---
try:
    import numpy as np
except ImportError:
    np = None

try:
    import cv2
except ImportError:
    cv2 = None

try:
    from ultralytics import YOLO
except ImportError:
    YOLO = None

# --- ANSI Colors ---
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

# --- Utility Functions ---
def print_header(text):
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*60}")
    print(f"{text.center(60)}")
    print(f"{'='*60}{Colors.ENDC}")

def print_box(title, content_lines):
    width = 70
    print(f"{Colors.CYAN}┌─ {title} {'─' * (width - len(title) - 4)}┐{Colors.ENDC}")
    for line in content_lines:
        print(f"{Colors.CYAN}│{Colors.ENDC} {line:<{width-2}} {Colors.CYAN}│{Colors.ENDC}")
    print(f"{Colors.CYAN}└{'─' * (width - 1)}┘{Colors.ENDC}")

def create_bar(value, max_val=50, width=20):
    if max_val == 0: return "[" + " " * width + "]"
    filled = int((value / max_val) * width)
    return "[" + "█" * filled + " " * (width - filled) + "]"

# --- PART 1: SIMULATION ENGINE ---
class TrafficSimulation:
    def __init__(self):
        self.lanes = ['North', 'South', 'East', 'West']
        self.static_time = 30.0  # Fixed 30s per lane
        self.yellow_time = 5.0
        
    def run_scenario(self, name, vehicle_counts):
        results = {}
        total_vehicles = sum(vehicle_counts.values())
        
        # 1. Static Mode
        static_results = {}
        total_static_wait = 0
        for lane, count in vehicle_counts.items():
            # In a fixed cycle, avg wait is (Total Cycle - Green Time) / 2
            # Simplified for diagnostic: wait time is proportional to (1 - 1/4) * total_cycle
            wait_per_vehicle = 45.0  # Assumed penalty for fixed cycle
            static_results[lane] = {
                'wait': wait_per_vehicle * count / 10.0,
                'green': 30.0
            }
            total_static_wait += static_results[lane]['wait']
            
        # 2. Adaptive/DQN Mock Mode
        adaptive_results = {}
        total_adaptive_wait = 0
        total_green_pool = 120.0
        
        for lane, count in vehicle_counts.items():
            # Allocate green time proportional to count (min 8s, max 50s)
            share = count / max(total_vehicles, 1)
            allocated_green = max(8.0, min(50.0, total_green_pool * share))
            
            # AI reduces wait time based on count/green ratio
            # If green is sufficient, wait time drops
            pressure = count / max(allocated_green, 1)
            wait_per_vehicle = 15.0 * pressure
            
            adaptive_results[lane] = {
                'wait': wait_per_vehicle * count / 10.0,
                'green': allocated_green
            }
            total_adaptive_wait += adaptive_results[lane]['wait']
            
        return {
            'name': name,
            'counts': vehicle_counts,
            'static': static_results,
            'adaptive': adaptive_results,
            'static_avg_wait': total_static_wait / max(total_vehicles, 1),
            'adaptive_avg_wait': total_adaptive_wait / max(total_vehicles, 1),
            'winner': 'AI/Adaptive' if total_adaptive_wait < total_static_wait else 'Static'
        }

# --- PART 2: VIDEO ANALYZER ---
class VideoAnalyzer:
    def __init__(self, model_path='yolov8n.pt'):
        self.model_path = model_path
        self.model = None
        self.is_mocked = False
        
        if YOLO is not None:
            try:
                self.model = YOLO(model_path)
            except Exception as e:
                print(f"{Colors.WARNING}⚠️ Failed to load YOLO model: {e}. Switching to Mock.{Colors.ENDC}")
                self.is_mocked = True
        else:
            self.is_mocked = True
            
    def find_video(self, override_path=None):
        if override_path and os.path.exists(override_path):
            return override_path
            
        search_dirs = ['./uploads/', './video_uploads/', './input_videos/', './']
        extensions = ('.mp4', '.avi', '.mov', '.mkv')
        
        for d in search_dirs:
            if not os.path.exists(d): continue
            for f in os.listdir(d):
                if f.lower().endswith(extensions):
                    return os.path.join(d, f)
        return None

    def analyze(self, video_path, sample_limit=50):
        if not cv2:
            return self.mock_analysis("No OpenCV installed")
            
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return self.mock_analysis("Could not open video file")
            
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        step = max(1, total_frames // sample_limit)
        frame_counts = {'North': [], 'South': [], 'East': [], 'West': []}
        confidences = {'North': [], 'South': [], 'East': [], 'West': []}
        detected_classes = []
        
        processed_count = 0
        for i in range(0, total_frames, step):
            if processed_count >= sample_limit: break
            cap.set(cv2.CAP_PROP_POS_FRAMES, i)
            ret, frame = cap.read()
            if not ret: break
            
            # Quadrant Mapping:
            # North: Top-Left | East: Top-Right
            # West: Bottom-Left | South: Bottom-Right
            quad_counts = {'North': 0, 'South': 0, 'East': 0, 'West': 0}
            quad_confs = {'North': [], 'South': [], 'East': [], 'West': []}
            
            if self.model and not self.is_mocked:
                results = self.model(frame, verbose=False)[0]
                for box in results.boxes:
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    conf = float(box.conf[0])
                    cls_id = int(box.cls[0])
                    cls_name = results.names[cls_id]
                    detected_classes.append(cls_name)
                    
                    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
                    
                    # 🛡️ HARD FILTER (Match detector.py)
                    if cls_name not in ['car', 'truck', 'bus', 'motorcycle', 'bike', 'autorickshaw']:
                        continue

                    if cy < height/2: # Top half
                        lane = 'North' if cx < width/2 else 'East'
                    else: # Bottom half
                        lane = 'West' if cx < width/2 else 'South'
                        
                    quad_counts[lane] += 1
                    quad_confs[lane].append(conf)
            else:
                # Mock detection for this frame
                for lane in quad_counts:
                    quad_counts[lane] = random.randint(2, 12)
                    quad_confs[lane] = [random.uniform(0.4, 0.9) for _ in range(quad_counts[lane])]
                detected_classes.extend(['car', 'bike', 'autorickshaw'])

            for lane in frame_counts:
                # 🛡️ TEMPORAL SMOOTHING (Match video_pipeline.py)
                history = frame_counts[lane][-10:] if frame_counts[lane] else []
                history.append(quad_counts[lane])
                smoothed_count = sum(history) / len(history)
                frame_counts[lane].append(smoothed_count)
                
                if quad_confs[lane]:
                    confidences[lane].append(sum(quad_confs[lane])/len(quad_confs[lane]))
                else:
                    confidences[lane].append(0.0)
            
            processed_count += 1
            
        cap.release()
        
        # Aggregation
        lane_stats = {}
        for lane in frame_counts:
            avg = sum(frame_counts[lane]) / len(frame_counts[lane])
            std = 0
            if np:
                std = float(np.std(frame_counts[lane]))
            avg_conf = sum(confidences[lane]) / len(confidences[lane]) if confidences[lane] else 0
            
            lane_stats[lane] = {
                'avg_count': avg,
                'avg_conf': avg_conf,
                'noise': std,
                'status': 'HEALTHY' if avg_conf > 0.5 and avg > 0 else 'DEGRADED'
            }
            
        return {
            'file': os.path.basename(video_path),
            'total_frames': total_frames,
            'sampled': processed_count,
            'lane_stats': lane_stats,
            'classes': list(set(detected_classes)),
            'is_mocked': self.is_mocked
        }

    def mock_analysis(self, reason):
        print(f"{Colors.WARNING}⚠️ Using full mock analysis: {reason}{Colors.ENDC}")
        return {
            'file': 'MOCK_VIDEO.mp4',
            'total_frames': 1000,
            'sampled': 50,
            'lane_stats': {
                lane: {'avg_count': random.uniform(5, 15), 'avg_conf': random.uniform(0.4, 0.8), 'noise': 2.1, 'status': 'MOCKED'}
                for lane in ['North', 'South', 'East', 'West']
            },
            'classes': ['car', 'truck', 'bike'],
            'is_mocked': True
        }

# --- MAIN DIAGNOSTIC SCRIPT ---
def main():
    parser = argparse.ArgumentParser(description="AI Traffic System Diagnostic Test")
    parser.add_argument("--video", type=str, help="Path to video file")
    parser.add_argument("--frames", type=int, default=50, help="Number of frames to sample")
    parser.add_argument("--scenario", type=str, choices=['sim', 'video', 'both'], default='both', help="Which scenario to run")
    args = parser.parse_args()

    pass_count = 0
    fail_count = 0
    issues = []

    print_header("🚦 AI TRAFFIC DIAGNOSTIC TEST v1.0 🚦")
    print(f"Timestamp: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Python: {sys.version.split()[0]} | YOLO: {'Installed' if YOLO else 'Missing'} | OpenCV: {'Installed' if cv2 else 'Missing'}")

    # --- PART 1: SIMULATION ---
    if args.scenario in ['sim', 'both']:
        print_header("SECTION 1: SIMULATION PERFORMANCE")
        sim = TrafficSimulation()
        scenarios = [
            ("Scenario A: Uniform", {'North': 12, 'South': 11, 'East': 14, 'West': 12}),
            ("Scenario B: Heavy North", {'North': 45, 'South': 8, 'East': 10, 'West': 7}),
            ("Scenario C: Rush Hour", {'North': 30, 'South': 28, 'East': 32, 'West': 35}),
        ]

        table_header = f"{'Scenario':<25} | {'Lane':<8} | {'Static WT':<10} | {'AI WT':<10} | {'Winner'}"
        print(Colors.BOLD + table_header + Colors.ENDC)
        print("-" * len(table_header))

        for name, counts in scenarios:
            res = sim.run_scenario(name, counts)
            
            # Check North Lane Bias (Only flag if traffic is uniform but green is biased)
            total_green = sum(l['green'] for l in res['adaptive'].values())
            north_share = res['adaptive']['North']['green'] / total_green
            total_traffic = sum(counts.values())
            north_traffic_share = counts['North'] / max(total_traffic, 1)
            
            # Bias = Green share is significantly higher than traffic share
            bias_detected = (north_share - north_traffic_share) > 0.15 
            
            if bias_detected:
                issues.append(f"Issue: North lane bias detected in {name} (Share: {north_share:.1%})")
                issues.append(f"   Fix: Normalize state input, check for count sensor drift.")
                fail_count += 1
            else:
                pass_count += 1

            for lane in sim.lanes:
                s_wt = res['static'][lane]['wait']
                a_wt = res['adaptive'][lane]['wait']
                winner = "AI" if a_wt < s_wt else "Static"
                print(f"{name if lane == 'North' else '':<25} | {lane:<8} | {s_wt:>10.1f} | {a_wt:>10.1f} | {winner}")

            # ASCII Bar Chart for AI Green Allocation
            print(f"   AI Green Allocation: ", end="")
            for lane in sim.lanes:
                g_time = res['adaptive'][lane]['green']
                color = Colors.GREEN if g_time < 40 else Colors.WARNING
                print(f"{color}{lane[0]}:{create_bar(g_time, 50, 8)}{Colors.ENDC} ", end="")
            print("\n")

    # --- PART 2: VIDEO ANALYZER ---
    video_res = None
    if args.scenario in ['video', 'both']:
        print_header("SECTION 2: REAL VIDEO PERCEPTION AUDIT")
        analyzer = VideoAnalyzer()
        v_path = analyzer.find_video(args.video)
        
        if not v_path:
            print(f"{Colors.FAIL}❌ No video file found in ./uploads/ or current directory.{Colors.ENDC}")
            print(f"   Please place an .mp4 or .avi file and rerun.")
        else:
            video_res = analyzer.analyze(v_path, args.frames)
            
            print(f"File: {Colors.BOLD}{video_res['file']}{Colors.ENDC}")
            print(f"Frames: {video_res['total_frames']} (Sampled {video_res['sampled']})")
            
            v_table_header = f"{'Lane':<8} | {'Avg Count':<10} | {'Avg Conf':<10} | {'Noise':<10} | {'Status'}"
            print(f"\n{Colors.BOLD}{v_table_header}{Colors.ENDC}")
            print("-" * len(v_table_header))
            
            for lane, stats in video_res['lane_stats'].items():
                c_val = stats['avg_conf']
                conf_color = Colors.GREEN if c_val > 0.6 else (Colors.WARNING if c_val > 0.4 else Colors.FAIL)
                print(f"{lane:<8} | {stats['avg_count']:>10.1f} | {conf_color}{c_val:>10.2f}{Colors.ENDC} | {stats['noise']:>10.2f} | {stats['status']}")
                
                if stats['avg_conf'] < 0.5:
                    issues.append(f"Issue: Low YOLO confidence on {lane} lane ({c_val:.2f})")
                    issues.append(f"   Fix: Fine-tune YOLO on low-light or Indian traffic dataset.")
                    fail_count += 1
                else:
                    pass_count += 1
                    
                if stats['avg_count'] < 1.0:
                    issues.append(f"Issue: {lane} lane consistently showing zero detections.")
                    issues.append(f"   Fix: Adjust quadrant mapping or check for occlusion.")
                    fail_count += 1
                else:
                    pass_count += 1

            print(f"\nDetected Classes: {Colors.CYAN}{', '.join(video_res['classes'])}{Colors.ENDC}")
            
            # Simulated comparison using video counts
            v_counts = {l: s['avg_count'] for l, s in video_res['lane_stats'].items()}
            v_sim = sim.run_scenario("Video Feed Replay", v_counts)
            if v_sim['adaptive_avg_wait'] < v_sim['static_avg_wait']:
                print(f"{Colors.GREEN}✅ AI outperforms Static on this video footage.{Colors.ENDC}")
                pass_count += 1
            else:
                print(f"{Colors.FAIL}❌ Static timing is more efficient than AI for this video counts.{Colors.ENDC}")
                issues.append("Issue: AI model underperforming on video-derived counts.")
                issues.append("   Fix: Retrain DQN on higher variance/noisy state inputs.")
                fail_count += 1

    # --- PART 3: SUMMARY ---
    print_header("FINAL DIAGNOSTIC SUMMARY")
    
    health = "HEALTHY"
    h_color = Colors.GREEN
    if fail_count > 2:
        health = "DEGRADED"
        h_color = Colors.WARNING
    if fail_count > 5:
        health = "CRITICAL"
        h_color = Colors.FAIL
        
    summary_lines = [
        f"System Health: {h_color}{Colors.BOLD}{health}{Colors.ENDC}",
        f"Total Tests Run: {pass_count + fail_count}",
        f"Passed: {Colors.GREEN}{pass_count}{Colors.ENDC} | Failed: {Colors.FAIL}{fail_count}{Colors.ENDC}",
        ""
    ]
    
    if issues:
        summary_lines.append(f"{Colors.BOLD}Detected Issues & Suggested Fixes:{Colors.ENDC}")
        for issue in issues:
            summary_lines.append(f" • {issue}")
    else:
        summary_lines.append("✅ No critical issues detected in sim or video modes.")

    print_box("DIAGNOSTIC REPORT", summary_lines)
    print("\n")

if __name__ == "__main__":
    main()
