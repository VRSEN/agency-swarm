"""Web Search Example

This example shows how to:
- search the web with `WebSearchTool`
- limit results to trusted OpenAI domains
- print the source URLs used during search

Run:
    uv run python examples/web_search.py

Requires OPENAI_API_KEY (or .env). Uses live API (network + usage).
"""

from __future__ import annotations

import asyncio
from datetime import datetime

from agents.items import ToolCallItem
from dotenv import load_dotenv
from openai.types.responses import ResponseFunctionWebSearch
from openai.types.responses.response_function_web_search import ActionSearch
from openai.types.responses.web_search_tool import Filters

from agency_swarm import Agency, Agent, RunResult, WebSearchTool

load_dotenv(override=True)


async def main() -> None:
    print("Simple WebSearch Example")
    print("=" * 25)

    research_agent = Agent(
        name="ResearchAgent",
        model="gpt-5-mini",
        instructions=(
            "You are a helpful assistant. Search OpenAI resources only and return a short summary "
            "for developers in 3 bullet points."
        ),
        tools=[
            WebSearchTool(
                filters=Filters(
                    allowed_domains=[
                        "openai.com",
                        "developer.openai.com",
                        "platform.openai.com",
                        "help.openai.com",
                    ]
                ),
                search_context_size="medium",
            )
        ],
    )
    agency = Agency(research_agent, shared_instructions="Demonstrate web search with sources.")

    today = datetime.now().strftime("%Y-%m-%d")
    query = f"What are 3 recent OpenAI platform updates for developers from the last few weeks? Today is {today}."
    print(f"\n❓ Query: {query}")
    response = await agency.get_response(query)

    print("\n### Final answer ###")
    print(response.final_output)

    source_urls = _extract_source_urls(response)
    print("\n### Sources ###")
    if not source_urls:
        print("No source URLs were returned.")
        return
    for url in source_urls:
        print(f"  - {url}")
    print(f"\nTotal sources: {len(source_urls)}")


def _extract_source_urls(response: RunResult) -> list[str]:
    """Extract unique source URLs from WebSearchTool calls."""
    unique_urls: list[str] = []
    seen_urls: set[str] = set()

    for item in response.new_items or []:
        if not isinstance(item, ToolCallItem):
            continue
        raw_call = item.raw_item
        if not isinstance(raw_call, ResponseFunctionWebSearch):
            continue
        action = raw_call.action
        if not isinstance(action, ActionSearch) or not action.sources:
            continue
        for source in action.sources:
            url = source.url
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_urls.append(url)

    return unique_urls


if __name__ == "__main__":
    asyncio.run(main())
