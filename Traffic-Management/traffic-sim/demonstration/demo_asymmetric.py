import asyncio
from demonstration.demo_runner import DemoRunner

async def main():
    # Runs the Asymmetric traffic scenario for 60 seconds
    runner = DemoRunner(scenario_name='asymmetric', duration_seconds=60)
    await runner.run()

if __name__ == "__main__":
    asyncio.run(main())
