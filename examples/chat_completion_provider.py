#!/usr/bin/env python3
"""
Agency Swarm with Chat Completion Model Provider Demo

Demonstrates OpenAI Chat Completions model provider from Agents SDK
with multi-agent communication and tool usage.
"""

import asyncio
import logging
import os
import sys

# Path setup for standalone examples
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from agents import OpenAIChatCompletionsModel, function_tool
from openai import AsyncOpenAI

from agency_swarm import Agency, Agent

# Simple logging setup
logging.basicConfig(level=logging.WARNING, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# --- Custom Chat Completion Model Provider ---

custom_client = AsyncOpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    timeout=30,
    max_retries=3,
)

# Create model instances
manager_model = OpenAIChatCompletionsModel(model="gpt-4.1", openai_client=custom_client)
worker_model = OpenAIChatCompletionsModel(model="gpt-4.1-mini", openai_client=custom_client)

# --- Tools ---

task_storage = {}


@function_tool
def save_task(task_id: str, description: str, priority: str = "medium") -> str:
    """Save a task with ID, description and priority."""
    task_storage[task_id] = {"description": description, "priority": priority, "status": "pending"}
    return f"Saved task '{task_id}': {description} (priority: {priority})"


@function_tool
def get_task(task_id: str) -> str:
    """Retrieve a task by its ID."""
    task = task_storage.get(task_id)
    if task:
        return f"Task '{task_id}': {task['description']} (priority: {task['priority']}, status: {task['status']})"
    else:
        return f"Error: Task '{task_id}' not found."


@function_tool
def list_all_tasks() -> str:
    """List all tasks in storage."""
    if not task_storage:
        return "No tasks found."

    task_list = []
    for task_id, info in task_storage.items():
        task_list.append(f"- {task_id}: {info['description']} [{info['priority']}] ({info['status']})")

    return "Current tasks:\n" + "\n".join(task_list)


# --- Agents ---

manager = Agent(
    name="TaskManager",
    description="Manages tasks and coordinates with worker",
    instructions="You delegate task operations to TaskWorker. Be clear about which tools to use.",
    model=manager_model,
)

worker = Agent(
    name="TaskWorker",
    description="Handles task operations using tools",
    instructions="""You MUST use your tools for all operations:
    - save_task: to save new tasks
    - get_task: to retrieve specific tasks
    - list_all_tasks: to list all tasks

    Never respond without using the appropriate tool first.""",
    tools=[save_task, get_task, list_all_tasks],
    model=worker_model,
)

# --- Agency ---

agency = Agency(
    manager,
    communication_flows=[(manager, worker)],
    shared_instructions="Be helpful and accurate. Use tools when available.",
)

# --- Demo ---


async def run_demo():
    """Demonstrates Chat Completion model provider with multi-agent communication."""
    print("🚀 Agency Swarm - Chat Completion Model Provider Demo")
    print(f"🤖 Manager: {manager_model.model} | ⚡ Worker: {worker_model.model}")
    print("=" * 60)

    # Demo 1: Create task
    print("\n🔹 Creating a task")
    response1 = await agency.get_response("Create task PROJ001 for 'Design UI mockups' with high priority")
    print(f"✅ {response1.final_output}")

    # Demo 2: List tasks
    print("\n🔹 Listing all tasks")
    response2 = await agency.get_response("Show all tasks")
    print(f"📋 {response2.final_output}")

    # Demo 3: Get specific task
    print("\n🔹 Getting task details")
    response3 = await agency.get_response("Get details for PROJ001")
    print(f"📄 {response3.final_output}")

    # Summary
    print(f"\n✅ Demo complete! Created {len(task_storage)} task(s)")
    print("🎯 Successfully demonstrated custom Chat Completion providers!")


async def main():
    """Main function."""
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ Set OPENAI_API_KEY environment variable")
        sys.exit(1)

    try:
        await run_demo()
    except Exception as e:
        logger.error(f"Demo failed: {e}")
        print(f"❌ Demo failed: {e}")


if __name__ == "__main__":
    asyncio.run(main())
