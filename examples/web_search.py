"""Web Search Example

This example shows how to:
- search the web with `WebSearchTool`
- limit results to trusted OpenAI domains
- print the source URLs used during search

Run:
    uv run python examples/web_search.py

Requires OPENAI_API_KEY (or .env). Uses live API (network + usage).
"""

import asyncio

from openai.types.responses.web_search_tool import Filters

from agency_swarm import Agency, Agent, WebSearchTool
from agency_swarm.utils.citation_extractor import extract_web_search_sources


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

    query = "What are 3 recent OpenAI platform updates for developers from the last few weeks?"
    print(f"\n❓ Query: {query}")
    response = await agency.get_response(query)

    print("\n### Final answer ###")
    print(response.final_output)

    source_urls = extract_web_search_sources(response)
    print("\n### Sources ###")
    if not source_urls:
        print("No source URLs were returned.")
        return
    for url in source_urls:
        print(f"  - {url}")
    print(f"\nTotal sources: {len(source_urls)}")


if __name__ == "__main__":
    asyncio.run(main())
