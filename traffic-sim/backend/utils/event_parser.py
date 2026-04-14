
# Parse event log for vehicle events (support camelCase and snake_case keys)
def parse_event_log(events):
	filtered = []
	for event in events or []:
		if not isinstance(event, dict):
			continue
		if event.get('event_type') in ('vehicle_added', 'vehicle_crossed') or event.get('eventType') in ('vehicle_added', 'vehicle_crossed'):
			filtered.append(event)
	result = []
	for event in filtered:
		# Support both camelCase and snake_case keys
		vehicle_id = event.get('vehicle_id') or event.get('vehicleId')
		vehicle_type = event.get('vehicle_type') or event.get('vehicleType')
		lane_id = event.get('lane_id') or event.get('laneId')
		event_type = event.get('event_type') or event.get('eventType')
		timestamp = event.get('timestamp', 0)
		result.append({
			'vehicleId': vehicle_id,
			'vehicleType': vehicle_type,
			'laneId': lane_id,
			'eventType': event_type,
			'timestamp': timestamp
		})
	return result

# Reconstruct vehicle timeline from parsed events
def reconstruct_vehicle_timeline(parsed_events):
	timeline = {'north': [], 'south': [], 'east': [], 'west': []}
	for event in parsed_events:
		if event.get('eventType') == 'vehicle_added':
			lane_id = event.get('laneId') or event.get('lane_id')
			if lane_id and lane_id in timeline:
				ts = event.get('timestamp')
				arrived_at = ts / 1000 if ts and ts > 1000000000000 else ts
				timeline[lane_id].append({
					'vehicleId': event.get('vehicleId'),
					'vehicleType': event.get('vehicleType'),
					'arrivedAt': arrived_at
				})
	return timeline
