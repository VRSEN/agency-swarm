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
from urllib.parse import urlparse

from openai.types.responses.web_search_tool import Filters

from agency_swarm import Agency, Agent, WebSearchTool
from agency_swarm.utils.citation_extractor import extract_web_search_sources

ALLOWED_DOMAINS = {
    "openai.com",
    "developer.openai.com",
    "platform.openai.com",
    "help.openai.com",
}


def validate_sources(source_urls: list[str]) -> None:
    """Require web-search citations from the configured OpenAI domains."""
    if not source_urls:
        raise RuntimeError("Web search returned no source URLs; the example did not prove live source retrieval.")

    unexpected_domains = sorted(
        {
            urlparse(url).netloc.removeprefix("www.")
            for url in source_urls
            if urlparse(url).netloc.removeprefix("www.") not in ALLOWED_DOMAINS
        }
    )
    if unexpected_domains:
        raise RuntimeError(f"Web search returned sources outside the allowed domains: {unexpected_domains}")


async def main() -> None:
    print("Simple WebSearch Example")
    print("=" * 25)

    research_agent = Agent(
        name="ResearchAgent",
        model="gpt-5.4-mini",
        instructions=(
            "You are a helpful assistant. Search OpenAI resources only and return a short summary "
            "for developers in 3 bullet points."
        ),
        tools=[
            WebSearchTool(
                filters=Filters(
                    allowed_domains=sorted(ALLOWED_DOMAINS),
                ),
                search_context_size="medium",
            )
        ],
    )
    agency = Agency(research_agent, shared_instructions="Demonstrate web search with sources.")

    query = (
        "Using current OpenAI docs only, explain what the Responses API web search tool does "
        "and how allowed_domains restricts the search. Answer in exactly 3 developer-focused bullets."
    )
    print(f"\n❓ Query: {query}")
    response = await agency.get_response(query)

    print("\n### Final answer ###")
    print(response.final_output)

    source_urls = extract_web_search_sources(response)
    validate_sources(source_urls)
    print("\n### Sources ###")
    for url in source_urls:
        print(f"  - {url}")
    print(f"\nTotal sources: {len(source_urls)}")


if __name__ == "__main__":
    asyncio.run(main())
