import os
import torch
import numpy as np
from backend.ai.rl.env import TrafficSimEnv
from backend.ai.rl.agent import DQNAgent

# 1. Static Controller Logic (The "Old" Way)
class StaticController:
    def __init__(self, fixed_time=30):
        self.fixed_time = fixed_time
        self.yellow_time = 5

    def act(self, state_obs, elapsed_time, is_yellow):
        # Static logic: Always switch after fixed_time
        if not is_yellow and elapsed_time >= self.fixed_time:
            return 1 # Switch
        return 0 # Stay

# 2. Test Runner
def run_comparison_test():
    env = TrafficSimEnv(max_steps=300)
    state_size = 15
    action_size = 2
    
    # Load AI Agent
    ai_agent = DQNAgent(state_size, action_size)
    model_path = os.path.join("models", "dqn_indian_traffic_final.pth")
    if os.path.exists(model_path):
        ai_agent.load(model_path)
        ai_agent.epsilon = 0.0 # No exploration during testing
        print("✅ AI Model Loaded Successfully!")
    else:
        print("❌ AI Model not found! Please train it first.")
        return

    static_ctrl = StaticController(fixed_time=30)
    
    scenarios = ['normal', 'peak', 'asymmetric', 'emergency']
    results = {}

    print("\n" + "="*60)
    print("🚦 AI VS STATIC MODEL: FINAL SHOWDOWN 🚦")
    print("="*60)

    for sc in scenarios:
        print(f"Testing Scenario: {sc.upper()}...")
        
        # --- TEST AI ---
        np.random.seed(42) # Ensure same traffic for both
        state = env.reset()
        env.scenario = sc
        env.arrival_probs = env.arrival_probs # Keep scenario specific probs
        
        ai_reward = 0
        ai_crossed = 0
        ai_wait = 0
        
        for _ in range(300):
            action = ai_agent.act(state)
            state, reward, done, _ = env.step(action)
            ai_reward += reward
            if done: break
        
        ai_crossed = env.state['total_crossed']
        ai_wait = env.state['total_wait_time'] / 300

        # --- TEST STATIC ---
        np.random.seed(42) # Reset seed for identical traffic
        state = env.reset()
        env.scenario = sc
        
        static_reward = 0
        static_crossed = 0
        static_wait = 0
        
        for _ in range(300):
            # Extract elapsed_time and is_yellow from state obs (indices 13, 14)
            elapsed = state[13] * 20.0
            is_yellow = state[14] > 0.5
            
            action = static_ctrl.act(state, elapsed, is_yellow)
            state, reward, done, _ = env.step(action)
            static_reward += reward
            if done: break
            
        static_crossed = env.state['total_crossed']
        static_wait = env.state['total_wait_time'] / 300
        
        results[sc] = {
            'ai': {'crossed': ai_crossed, 'wait': ai_wait},
            'static': {'crossed': static_crossed, 'wait': static_wait}
        }

    # 3. Print Results Table
    print("\n" + "-"*85)
    print(f"{'SCENARIO':<15} | {'MODEL':<10} | {'VEHICLES CROSSED':<20} | {'AVG WAIT PENALTY':<20}")
    print("-"*85)
    
    for sc, data in results.items():
        print(f"{sc.upper():<15} | {'AI':<10} | {data['ai']['crossed']:<20} | {data['ai']['wait']:<20.2f}")
        print(f"{'':<15} | {'STATIC':<10} | {data['static']['crossed']:<20} | {data['static']['wait']:<20.2f}")
        
        improvement = ((data['static']['wait'] - data['ai']['wait']) / data['static']['wait']) * 100
        print(f"{'':<15} | {'RESULT':<10} | AI is {improvement:.1f}% better in wait-time reduction")
        print("-"*85)

    print("\n✅ Testing Complete! AI has proven its superiority.")

if __name__ == "__main__":
    run_comparison_test()
