import threading

latest_results_lock = threading.Lock()
latest_results = {
    'lane_counts': [0, 0, 0, 0],
}
