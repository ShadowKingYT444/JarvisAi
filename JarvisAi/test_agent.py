
import asyncio
from agent import BrowserAgent

async def main():
    print("Test 1: Simple Math")
    agent = BrowserAgent()
    await agent.start()
    # Mocking the loop without input()
    # We just run one command
    try:
        await agent.run_loop("What is 2 + 2?")
        
        print("\nTest 2: Browser Navigation")
        await agent.run_loop("Open example.com")
    finally:
        await agent.stop()

if __name__ == "__main__":
    asyncio.run(main())
