import asyncio
from demonstration.demo_runner import DemoRunner

async def main():
    # Runs the Emergency traffic scenario for 60 seconds
    runner = DemoRunner(scenario_name='emergency', duration_seconds=60)
    await runner.run()

if __name__ == "__main__":
    asyncio.run(main())
