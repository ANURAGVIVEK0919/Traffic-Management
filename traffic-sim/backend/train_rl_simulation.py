import random
import time

import backend.controllers.rl_controller as rl_controller


TRAFFIC_DIRECTIONS = ['north', 'south', 'east', 'west']


def generate_smart_traffic():
	"""Generate richer traffic scenarios for better policy learning."""
	base = {direction: random.randint(2, 6) for direction in TRAFFIC_DIRECTIONS}

	lane = random.choice(TRAFFIC_DIRECTIONS)
	base[lane] += random.randint(15, 30)

	line_counts = base
	wait_time = {
		direction: line_counts[direction] * random.uniform(4, 10)
		for direction in TRAFFIC_DIRECTIONS
	}
	queue_length = {
		direction: max(0, line_counts[direction] - random.randint(2, 5))
		for direction in TRAFFIC_DIRECTIONS
	}

	return {
		'line_counts': line_counts,
		'wait_time_by_direction': wait_time,
		'queue_length_by_direction': queue_length,
		'active_green_lane': random.choice(TRAFFIC_DIRECTIONS),
		'timestamp': time.time(),
	}


def train_rl(steps=15000):
	rl_controller.INFERENCE_MODE = False
	print('🚀 Starting RL training...')

	for step in range(steps):
		request = generate_smart_traffic()
		decision = rl_controller.handle_rl_decision(request)

		if step % 100 == 0:
			print('\n===== TRAINING STEP =====')
			print('Step:', step)
			print('Counts:', request['line_counts'])
			print('Wait:', request['wait_time_by_direction'])
			print('Queue:', request['queue_length_by_direction'])
			print('Decision:', decision['lane'])
			print('========================\n')

	print('✅ Training complete!')
	print('Model saved at models/final_dqn_model.pth')


if __name__ == '__main__':
	train_rl(steps=15000)
