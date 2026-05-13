"""
V2I Service — The Central Hub for Digital Beacon Tracking.
Calculates ETA and manages early-warning states for the intersection.
"""

import time
from typing import Dict, List, Optional
from pydantic import BaseModel

class V2IBeacon(BaseModel):
    vehicle_id: str
    lane: str
    distance: float  # meters
    speed: float     # m/s
    last_update: float
    eta: float       # seconds remaining

_beacons: Dict[str, V2IBeacon] = {}

def process_beacon_signal(vehicle_id: str, lane: str, distance: float, speed: float = 15.0):
    """Update beacon data and calculate ETA."""
    eta = distance / speed if speed > 0 else 999
    _beacons[vehicle_id] = V2IBeacon(
        vehicle_id=vehicle_id,
        lane=lane,
        distance=distance,
        speed=speed,
        last_update=time.time(),
        eta=eta
    )
    print(f"📡 [V2I HUB] {vehicle_id} detected in {lane.upper()} lane. ETA: {eta:.1f}s")

def get_v2i_status() -> List[dict]:
    """Clean up old beacons and return active ones."""
    now = time.time()
    active = []
    to_delete = []
    
    for vid, b in _beacons.items():
        # If no signal for 5 seconds, assume out of range or passed
        if now - b.last_update > 5.0:
            to_delete.append(vid)
            continue
            
        # Dynamic ETA update based on elapsed time since last signal
        elapsed = now - b.last_update
        current_eta = max(0, b.eta - elapsed)
        
        active.append({
            "vehicle_id": b.vehicle_id,
            "lane": b.lane,
            "eta": round(current_eta, 1),
            "distance": round(b.distance - (b.speed * elapsed), 1)
        })
        
    for vid in to_delete:
        del _beacons[vid]
        
    return active

def get_urgent_preemption_lane() -> Optional[str]:
    """Returns the lane that needs immediate attention."""
    status = get_v2i_status()
    if not status:
        return None
    # Prioritize the vehicle with the lowest ETA
    status.sort(key=lambda x: x['eta'])
    return status[0]['lane']
