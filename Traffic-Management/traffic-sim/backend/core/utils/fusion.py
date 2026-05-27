def fuse_emergency_signals(visual_detected, gps_data, audio_level):
    """
    Fuses multiple signals to detect an ambulance.
    visual_detected: bool (YOLO detection)
    gps_data: dict or None (e.g., {'distance': 100, 'speed': 15})
    audio_level: float (decibels normalized 0-1)
    
    Returns: bool (True if ambulance presence is confirmed by fusion)
    """
    # 1. Visual is strongest signal
    if visual_detected:
        return True
        
    # 2. GPS + Audio Fusion
    # If GPS reports an ambulance within 200m AND audio is high (> 0.6)
    if gps_data and isinstance(gps_data, dict):
        distance = gps_data.get('distance', 1000)
        if distance < 200 and audio_level > 0.4:
            return True
            
    # 3. Very High Audio (e.g., siren very close but not visible)
    if audio_level > 0.8:
        return True
        
    return False

def get_fused_ambulance_state(visual_map, gps_map, audio_map):
    """
    Returns a fused boolean map for all lanes.
    """
    fused_state = {}
    lanes = ['north', 'east', 'south', 'west']
    for lane in lanes:
        fused_state[lane] = fuse_emergency_signals(
            visual_map.get(lane, False),
            gps_map.get(lane, None),
            audio_map.get(lane, 0.0)
        )
    return fused_state
