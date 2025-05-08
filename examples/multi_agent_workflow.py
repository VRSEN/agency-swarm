# examples/multi_agent_workflow.py
import asyncio
import logging
import os
import sys
from typing import Any

from agents import RunContextWrapper, function_tool
from pydantic import BaseModel, Field

# Configure basic logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from agency_swarm.agency import Agency
from agency_swarm.agent import Agent


# --- Define Tool Input Schemas (Pydantic) ---
class WebSearchInput(BaseModel):
    query: str = Field(..., description="The search query for the web.")


class SummarizeInput(BaseModel):
    text_snippets: list[str] = Field(..., description="List of text snippets to summarize.")


# --- Define Tools as Decorated Functions ---
@function_tool()
async def web_search(wrapper: RunContextWrapper[Any], query: str) -> dict[str, list[str]]:
    """Performs a web search for the given query and returns relevant text snippets.

    Args:
        wrapper: The run context wrapper.
        query: The search query for the web.
    """
    print(f"--- TOOL: web_search called with query: {query} ---")
    # Simulate finding results
    await asyncio.sleep(0.5)  # Simulate network latency
    results = [
        f"Snippet about {query} from source 1.",
        f"Another relevant piece of text regarding {query}.",
        f"Key finding related to {query} discussed here.",
    ]
    # Return value must match type hint or be string serializable
    return {"results": results}


@function_tool()
async def summarize_text(wrapper: RunContextWrapper[Any], text_snippets: list[str]) -> dict[str, str]:
    """Summarizes a list of text snippets into a concise paragraph.

    Args:
        wrapper: The run context wrapper.
        text_snippets: List of text snippets to summarize.
    """
    print(f"--- TOOL: summarize_text called with {len(text_snippets)} snippets ---")
    await asyncio.sleep(0.3)  # Simulate processing time
    summary = f"This is a concise summary based on {len(text_snippets)} snippets. The key theme is related to the input query."
    # Return value must match type hint or be string serializable
    return {"summary": summary}


# --- Define Agents (Using new tool instances) ---
researcher = Agent(
    name="Researcher",
    instructions="You are a research agent. Use the web_search tool to find information on a given topic.",
    tools=[web_search],  # Use the decorated function instance
)

synthesizer = Agent(
    name="Synthesizer",
    instructions="You receive research snippets from the Researcher. Use the summarize_text tool to create a concise summary.",
    tools=[summarize_text],  # Use the decorated function instance
)

writer = Agent(
    name="Writer",
    instructions="You receive a summary from the Synthesizer. Write a short report based on the summary.",
    # No specific tools needed, just uses LLM capabilities
)


# --- Define Agency Chart ---
# Flow: Researcher -> Synthesizer -> Writer
agency_chart = [
    researcher,  # Entry point
    [researcher, synthesizer],  # Researcher sends snippets to Synthesizer
    [synthesizer, writer],  # Synthesizer sends summary to Writer
]

# --- Create Agency Instance ---
agency = Agency(
    agency_chart=agency_chart,
    shared_instructions="Be thorough and accurate in your respective tasks.",
)

# --- Run Interaction ---


async def run_workflow():
    print("\n--- Running Multi-Agent Workflow Example ---")

    initial_topic = "the future of AI agents"

    print(f"\nUser Request to {researcher.name}: Research '{initial_topic}'")

    try:
        # Start the workflow by asking the Researcher
        response = await agency.get_response(
            message=f"Please research the topic: {initial_topic}",
            recipient_agent=researcher.name,  # Start with the researcher
        )

        # The final response should come from the last agent in the chain (Writer)
        if response:
            print(f"\nFinal Report from {writer.name}:")  # The writer is the final agent
            final_output = response.final_output
            print(f"  Output:\n{final_output if isinstance(final_output, str) else type(final_output)}")
            print(f"  Items Generated: {len(response.new_items)}")
        else:
            print("\nWorkflow did not produce a final response.")

    except Exception as e:
        logging.error(f"An error occurred during the workflow: {e}", exc_info=True)


# --- Main Execution ---
if __name__ == "__main__":
    if not os.getenv("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY environment variable not set.")
    else:
        asyncio.run(run_workflow())
