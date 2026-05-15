import asyncio
import os
from demonstration.demo_runner import DemoRunner

async def run_story_demo(scenario, title, story):
    os.system('cls' if os.name == 'nt' else 'clear')
    print("\n" + "🌟" * 40)
    print(f"📖 THE STORY: {title}")
    print(f"💡 {story}")
    print("🌟" * 40)
    print("\nStarting in 5 seconds...")
    await asyncio.sleep(5)
    
    runner = DemoRunner(scenario_name=scenario, duration_seconds=300)
    await runner.run()

async def main():
    while True:
        try:
            os.system('cls' if os.name == 'nt' else 'clear')
            print("="*50)
            print("🚦 AI TRAFFIC CONTROLLER: GOLDEN USE-CASES 🚦")
            print("="*50)
            print("1. [EFFICIENCY] Peak Hour - Jam Clearing")
            print("2. [SAFETY] Emergency - Ambulance Priority")
            print("3. [FAIRNESS] Asymmetric - Smart Lane Balancing")
            print("4. Exit")
            print("="*50)
            
            choice = input("Select a scenario to demonstrate (1-4): ")
        except EOFError:
            break
        
        if choice == '1':
            await run_story_demo(
                'peak', 
                'The Efficiency King', 
                'In heavy traffic, the AI optimizes every second to clear the jam 49% faster than static timers.'
            )
        elif choice == choice == '2':
            await run_story_demo(
                'emergency', 
                'The Life Saver', 
                'AI may show higher wait times here, but it wins because it NEVER blocks an ambulance. Safety over numbers.'
            )
        elif choice == '3':
            await run_story_demo(
                'asymmetric', 
                'The Fairness Master', 
                'When one lane is overloaded, AI smartly balances the green time to prevent a city-wide gridlock.'
            )
        elif choice == '4':
            break
        else:
            print("Invalid choice. Try again.")
            await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
