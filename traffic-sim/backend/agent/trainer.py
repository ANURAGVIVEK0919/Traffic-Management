# Import required modules
import torch
import torch.nn as nn
import random
import os
from backend.agent.rl_agent import TrafficRLAgent

# Training constants
EPISODES = 10000
STEPS_PER_EPISODE = 60
GAMMA = 0.95
LEARNING_RATE = 0.001
EPSILON_START = 1.0
EPSILON_END = 0.05
EPSILON_DECAY = 0.995
OUTPUT_MODEL_PATH = 'models/rl_model.pth'
LANE_ORDER = ['north', 'east', 'south', 'west']

# Indian traffic distribution constants
MAX_VEHICLES_PER_LANE = 8
AMBULANCE_PROBABILITY = 0.08
TWO_WHEELER_PROBABILITY = 0.45
HEAVY_VEHICLE_PROBABILITY = 0.15


def generate_lane_state():
    # Generate random lane state for Indian traffic
    lane_state = {}
    for lane in LANE_ORDER:
        # Weighted toward higher counts
        count = random.choices(
            range(MAX_VEHICLES_PER_LANE + 1),
            weights=[1,2,3,4,5,6,7,8,9]
        )[0]
        hasAmbulance = random.random() < AMBULANCE_PROBABILITY
        avgWaitTime = random.uniform(0, 30)
        ambulanceWaitTime = random.uniform(5, 20) if hasAmbulance else 0.0
        lane_state[lane] = {
            'count': count,
            'hasAmbulance': hasAmbulance,
            'avgWaitTime': avgWaitTime,
            'ambulanceWaitTime': ambulanceWaitTime
        }
    return lane_state


def lane_state_to_tensor(lane_state):
    # Flatten lane state to tensor
    values = []
    for lane in LANE_ORDER:
        values.append(lane_state[lane]['count'])
        values.append(float(lane_state[lane]['hasAmbulance']))
        values.append(lane_state[lane]['avgWaitTime'])
    return torch.FloatTensor(values)


def compute_reward(lane_state, chosen_lane):
    # Compute reward for chosen lane
    reward = 0.0
    if lane_state[chosen_lane]['hasAmbulance']:
        reward += 10
    elif any(lane_state[l]['hasAmbulance'] for l in LANE_ORDER if l != chosen_lane):
        reward -= 5
    reward += lane_state[chosen_lane]['count'] * 1.0
    if lane_state[chosen_lane]['count'] == 0:
        reward -= 2
    return reward


def train_rl_agent():
    # RL training loop
    agent = TrafficRLAgent()
    optimizer = torch.optim.Adam(agent.parameters(), lr=LEARNING_RATE)
    loss_fn = nn.MSELoss()
    epsilon = EPSILON_START
    for episode in range(EPISODES):
        for step in range(STEPS_PER_EPISODE):
            state = generate_lane_state()
            state_tensor = lane_state_to_tensor(state)
            # Epsilon-greedy action selection
            if random.random() < epsilon:
                action_idx = random.randint(0, 3)
            else:
                q_values = agent(state_tensor)
                action_idx = torch.argmax(q_values).item()
            chosen_lane = LANE_ORDER[action_idx]
            reward = compute_reward(state, chosen_lane)
            next_state = generate_lane_state()
            next_state_tensor = lane_state_to_tensor(next_state)
            next_q_values = agent(next_state_tensor)
            target = reward + GAMMA * torch.max(next_q_values).item()
            q_values = agent(state_tensor)
            current_q = q_values[action_idx]
            loss = loss_fn(current_q, torch.tensor(target))
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
        epsilon = max(EPSILON_END, epsilon * EPSILON_DECAY)
        if (episode + 1) % 1000 == 0:
            print(f"Episode {episode+1} complete. Epsilon: {epsilon:.3f}")
    torch.save(agent.state_dict(), OUTPUT_MODEL_PATH)
    print(f"RL training complete. Model saved to {OUTPUT_MODEL_PATH}")
    return OUTPUT_MODEL_PATH


if __name__ == '__main__':
    train_rl_agent()
