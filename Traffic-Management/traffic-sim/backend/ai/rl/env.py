import random
import numpy as np

class TrafficSimEnv:
    """
    Indian Traffic Scenario Environment (Rule-Strict):
    - Peak Hour: High density in all lanes
    - Asymmetric: Heavy load on one specific lane (common in India)
    - Emergency: High frequency of ambulances
    """
    def __init__(self, max_steps=400): 
        self.lanes = ['north', 'west', 'south', 'east']
        self.max_steps = max_steps
        self.min_green = 8
        self.max_green = 30
        self.yellow_time = 5
        self.initial_cycle_time = 10
        self.reset()

    def reset(self):
        # Indian Scenario Selection
        self.scenario = random.choice(['peak', 'normal', 'asymmetric', 'emergency'])
        self.arrival_probs = {lane: 0.2 for lane in self.lanes}
        
        if self.scenario == 'peak':
            self.arrival_probs = {lane: 0.4 for lane in self.lanes}
        elif self.scenario == 'asymmetric':
            busy_lane = random.choice(self.lanes)
            self.arrival_probs = {l: 0.1 for l in self.lanes}
            self.arrival_probs[busy_lane] = 0.6
        elif self.scenario == 'emergency':
            self.arrival_probs = {lane: 0.25 for lane in self.lanes}

        self.state = {
            'active_lane_idx': 0,
            'elapsed_time': 0,
            'is_yellow': False,
            'is_initial_cycle': True,
            'initial_lanes_done': 0,
            'total_wait_time': 0,
            'total_crossed': 0
        }
        self.queues = {lane: [] for lane in self.lanes}
        self.ambulances = {lane: False for lane in self.lanes}
        self.step_count = 0
        return self._get_obs()

    def _get_obs(self):
        obs = []
        for lane in self.lanes:
            obs.append(len(self.queues[lane]) / 25.0) # Scaled for higher density
        for lane in self.lanes:
            avg_wait = 0
            if self.queues[lane]:
                avg_wait = sum(self.step_count - t for t in self.queues[lane]) / len(self.queues[lane])
            obs.append(avg_wait / 80.0)
        for lane in self.lanes:
            obs.append(1.0 if self.ambulances[lane] else 0.0)
        obs.append(self.state['active_lane_idx'] / 3.0)
        obs.append(self.state['elapsed_time'] / 20.0)
        obs.append(1.0 if self.state['is_yellow'] else 0.0)
        return np.array(obs, dtype=np.float32)

    def step(self, action):
        active_lane = self.lanes[self.state['active_lane_idx']]
        reward = 0

        # 1. New Arrivals based on Indian Scenarios
        for lane in self.lanes:
            prob = self.arrival_probs[lane]
            if random.random() < prob:
                self.queues[lane].append(self.step_count)
                # Higher ambulance probability in 'emergency' scenario
                amb_prob = 0.15 if self.scenario == 'emergency' else 0.05
                if random.random() < amb_prob:
                    self.ambulances[lane] = True

        # 2. Phase Logic (Yellow/Green)
        if self.state['is_yellow']:
            self.state['elapsed_time'] += 1
            if self.state['elapsed_time'] >= self.yellow_time:
                self.state['is_yellow'] = False
                self.state['active_lane_idx'] = (self.state['active_lane_idx'] + 1) % 4
                self.state['elapsed_time'] = 0
                if self.state['is_initial_cycle']:
                    self.state['initial_lanes_done'] += 1
                    if self.state['initial_lanes_done'] >= 4:
                        self.state['is_initial_cycle'] = False
        else:
            self.state['elapsed_time'] += 1
            if self.state['is_initial_cycle']:
                if self.state['elapsed_time'] >= self.initial_cycle_time:
                    self.state['is_yellow'] = True
                    self.state['elapsed_time'] = 0
            else:
                if self.state['elapsed_time'] >= self.max_green:
                    self.state['is_yellow'] = True
                    self.state['elapsed_time'] = 0
                elif action == 1 and self.state['elapsed_time'] >= self.min_green:
                    self.state['is_yellow'] = True
                    self.state['elapsed_time'] = 0
                
        # 3. Physics (Crossings)
        # Vehicles cross during BOTH Green and Yellow phases
        # (Startup delay 3s only applies at the very beginning of Green)
        crossed_this_step = 0
        is_startup_delay = (not self.state['is_yellow'] and self.state['elapsed_time'] < 3)
        
        if not is_startup_delay:
            if self.queues[active_lane]:
                self.queues[active_lane].pop(0)
                crossed_this_step += 1
                self.state['total_crossed'] += 1
                if not any(v for v in self.queues[active_lane]):
                    self.ambulances[active_lane] = False

        # 4. Zero-Greed Wait Minimization (Focus: Fairness & Minimum Delay)
        # Use Squared-Wait Penalty to prevent any single lane from getting too long
        squared_wait_penalty = sum(len(self.queues[l])**2 for l in self.lanes)
        total_wait = sum(len(self.queues[l]) for l in self.lanes)
        self.state['total_wait_time'] += total_wait
        
        # Priority Penalty (Ambulance is highest priority)
        amb_penalty = sum(100 for l in self.lanes if self.ambulances[l] and l != active_lane)
        
        # Reward: NO reward for crossing. ONLY penalty for waiting.
        # This forces AI to rotate as quickly as possible to keep all queues short.
        reward = -(squared_wait_penalty * 0.5) - (total_wait * 1.0) - amb_penalty
        
        # Rule: Fair Lane Rotation & Green Utilization
        if not self.state['is_yellow'] and self.state['elapsed_time'] > self.min_green:
            if len(self.queues[active_lane]) == 0:
                reward -= 100  # Massive penalty for wasting green on empty lane
        
        # Penalty for violating MIN_GREEN
        if action == 1 and not self.state['is_yellow'] and self.state['elapsed_time'] < self.min_green:
            reward -= 200

        self.step_count += 1
        done = self.step_count >= self.max_steps
        
        # 5. XAI: Generate human-readable explanation
        explanation = self.generate_explanation(action, active_lane, total_wait, crossed_this_step)
        
        info = {
            'explanation': explanation,
            'metrics': self.state,
            'lane_queues': {l: len(self.queues[l]) for l in self.lanes}
        }
        
        return self._get_obs(), reward, done, info

    def generate_explanation(self, action, active_lane, total_wait, crossed):
        if self.state['is_yellow']:
            return f"Transitioning: Yellow phase for {active_lane} lane. Timer frozen."
            
        if action == 1: # SWITCH
            # Why did it switch?
            next_lane = self.lanes[(self.lanes.index(active_lane) + 1) % 4]
            if len(self.queues[active_lane]) == 0:
                return f"Switching: {active_lane} lane is empty. Moving to {next_lane} to save time."
            if any(self.ambulances[l] for l in self.lanes if l != active_lane):
                return f"Switching: EMERGENCY! Ambulance detected in another lane. Clearing path."
            if len(self.queues[next_lane]) > 10:
                return f"Switching: {next_lane} queue is too long ({len(self.queues[next_lane])}). Maintaining fairness."
            return f"Switching: Maximizing efficiency by rotating to {next_lane}."
        else: # STAY
            if self.ambulances[active_lane]:
                return f"Staying: Keeping {active_lane} Green to prioritize Ambulance crossing."
            if crossed > 0:
                return f"Staying: Traffic is flowing smoothly in {active_lane} lane."
            return f"Staying: {active_lane} lane still has vehicles to clear within safe limits."
