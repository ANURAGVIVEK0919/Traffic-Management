import threading

# Thread-safe in-memory state for real-time updates (WebSockets, UI polling)
latest_results = {}
latest_results_lock = threading.Lock()
