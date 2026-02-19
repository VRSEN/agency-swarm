"""Verify WebSearchTool sources extraction in Agency Swarm.

Run: uv run python examples/verify_web_search_sources.py
Requires OPENAI_API_KEY (or .env). Uses live API (network + usage).
"""

from __future__ import annotations

import asyncio

from agents import Runner
from dotenv import load_dotenv
from openai.types.responses import ResponseFunctionWebSearch
from openai.types.responses.response_function_web_search import ActionSearch

from agency_swarm import Agent, WebSearchTool

load_dotenv(override=True)


async def main() -> None:
    agent = Agent(
        name="ExampleAgent",
        model="gpt-5-mini",
        instructions="Just search and return the best option.",
        tools=[WebSearchTool()],
        include_web_search_sources=True,  # default behavior in Agency Swarm
    )

    result = await Runner.run(agent, "Find the best Toyota Corolla in Utah")

    print("### Final output ###")
    print(result.final_output)
    print()

    print("### Sources ###")
    sources_found = 0
    for item in result.new_items or []:
        raw_call = getattr(item, "raw_item", None)
        if not isinstance(raw_call, ResponseFunctionWebSearch):
            continue
        action = raw_call.action
        if not isinstance(action, ActionSearch) or not action.sources:
            continue
        for source in action.sources:
            url = source.url
            if url:
                print(f"  - {url}")
                sources_found += 1

    if sources_found == 0:
        print("  (no sources in response; response_include may not be supported for this model or response)")
    else:
        print(f"\nTotal sources: {sources_found}")


if __name__ == "__main__":
    asyncio.run(main())
