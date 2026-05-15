import os
import time
import asyncio
from backend.ai.rl.env import TrafficSimEnv
from backend.ai.rl.agent import DQNAgent
from backend.core.services.llm_service import explain_decision

class DemoRunner:
    def __init__(self, scenario_name, duration_seconds=60):
        self.scenario = scenario_name
        self.duration = duration_seconds
        self.env = TrafficSimEnv(max_steps=duration_seconds)
        self.env.scenario = scenario_name
        
        self.agent = DQNAgent(state_size=15, action_size=2)
        model_path = os.path.join("models", "dqn_indian_traffic_final.pth")
        if os.path.exists(model_path):
            self.agent.load(model_path)
            self.agent.epsilon = 0.0 # Strict policy for demo
        
    async def run(self):
        state = self.env.reset()
        print("\n" + "="*80)
        print(f"🚦 LIVE DEMONSTRATION: {self.scenario.upper()} SCENARIO 🚦")
        print(f"🕒 Duration: {self.duration} Seconds | Mode: Explainable AI (XAI)")
        print("="*80)
        
        last_switch_time = 0
        current_explanation = "Initializing AI model..."

        for step in range(self.duration):
            action = self.agent.act(state)
            
            # Extract info for LLM explanation
            lane_counts = {l: len(self.env.queues[l]) for l in self.env.lanes}
            wait_times = {l: (sum(step - t for t in self.env.queues[l])/len(self.env.queues[l]) if self.env.queues[l] else 0) for l in self.env.lanes}
            ambulance = self.env.ambulances
            active_lane = self.env.lanes[self.env.state['active_lane_idx']]
            
            # Get Explanation if decision changes or every 10 steps
            if action == 1 or step % 10 == 0:
                # Call Groq for real reasoning
                current_explanation = await explain_decision(
                    lane_counts, wait_times, ambulance, active_lane, self.env.state['elapsed_time']
                )

            # Step the environment
            state, reward, done, info = self.env.step(action)
            
            # --- UI DASHBOARD (Terminal) ---
            os.system('cls' if os.name == 'nt' else 'clear')
            print("="*80)
            print(f"SCENARIO: {self.scenario.upper()} | STEP: {step+1}/{self.duration}")
            print("-" * 80)
            
            # Lane Status Table
            print(f"{'LANE':<10} | {'STATUS':<10} | {'QUEUED':<10} | {'AMBULANCE':<10}")
            print("-" * 80)
            for l in self.env.lanes:
                status = "🟢 GREEN" if l == active_lane and not self.env.state['is_yellow'] else \
                         "🟡 YELLOW" if l == active_lane and self.env.state['is_yellow'] else "🔴 RED"
                amb = "🚑 YES" if self.env.ambulances[l] else "NO"
                print(f"{l.upper():<10} | {status:<10} | {len(self.env.queues[l]):<10} | {amb:<10}")
            
            print("-" * 80)
            print(f"📈 TOTAL CROSSED: {self.env.state['total_crossed']}")
            print("-" * 80)
            
            # AI REASONING BOX
            print(f"🤖 AI REASONING (Groq/Llama-3):")
            print(f"> {current_explanation}")
            print("="*80)
            
            await asyncio.sleep(1) # Live simulation speed
            if done: break

        print("\n✅ AI Demonstration Complete. Running Static Baseline for comparison...")
        static_metrics = self.run_static_baseline()
        
        # --- FINAL COMPARISON TABLE ---
        print("\n" + "="*80)
        print(f"📊 COMPARISON REPORT: {self.scenario.upper()} SCENARIO")
        print("="*80)
        print(f"{'METRIC':<25} | {'AI MODEL (DQN)':<20} | {'STATIC (30s)':<20}")
        print("-" * 80)
        
        ai_wait = self.env.state['total_wait_time'] / self.duration
        st_wait = static_metrics['total_wait_time'] / self.duration
        improvement = ((st_wait - ai_wait) / st_wait * 100) if st_wait > 0 else 0

        print(f"{'Vehicles Crossed':<25} | {self.env.state['total_crossed']:<20} | {static_metrics['total_crossed']:<20}")
        print(f"{'Average Wait Penalty':<25} | {ai_wait:<20.2f} | {st_wait:<20.2f}")
        print("-" * 80)
        print(f"🎯 VERDICT: AI is {improvement:.1f}% {'BETTER' if improvement > 0 else 'WORSE'} in wait-time reduction.")
        print("="*80)
        input("\nPress Enter to return to menu...")

    def run_static_baseline(self):
        """Runs a silent static 30s simulation for comparison"""
        env = TrafficSimEnv(max_steps=self.duration)
        env.scenario = self.scenario
        env.reset()
        
        for _ in range(self.duration):
            # Static Logic: Switch every 30s
            action = 0
            if env.state['elapsed_time'] >= 30 and not env.state['is_yellow']:
                action = 1
            env.step(action)
            
        return env.state
