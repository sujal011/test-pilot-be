import asyncio
from app.agents.browser_agent import browser_agent
import pprint

async def test():
    res = await browser_agent.execute_step("agent-browser open https://google.com", "test_run_123")
    pprint.pp(res)

if __name__ == "__main__":
    asyncio.run(test())
