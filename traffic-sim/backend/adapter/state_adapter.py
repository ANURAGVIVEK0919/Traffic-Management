def build_rl_state(extracted_state):
    lane_counts = extracted_state.get("lane_counts", {})

    rl_state = {
        "lane_counts": [
            lane_counts.get("north", 0),
            lane_counts.get("south", 0),
            lane_counts.get("east", 0),
            lane_counts.get("west", 0),
        ]
    }

    print("ADAPTER INPUT:", extracted_state.get("lane_counts"))
    print("ADAPTER OUTPUT:", rl_state)

    return rl_state