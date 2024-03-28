import importlib
from pathlib import Path
import re
from .list_available_agents import list_available_agents

def extract_description_from_file(file_path):
    """
    Extracts the agent's description from its Python file.
    """
    description_pattern = re.compile(
        r'\s*description\s*=\s*["\'](.*?)["\'],', re.DOTALL)
    with open(file_path, 'r', encoding='utf-8') as file:
        content = file.read()
    match = description_pattern.search(content)
    if match:
        description = ' '.join(match.group(1).split())
        return description
    return "Description not found."


def get_available_agent_descriptions():
    descriptions = {}

    # Dynamically get the path of the agency_swarm.agents module
    spec = importlib.util.find_spec("agency_swarm.agents")
    if spec is None or spec.origin is None:
        raise ImportError("Could not locate 'agency_swarm.agents' module.")
    agents_path = Path(spec.origin).parent

    agents = list_available_agents()
    for agent_name in agents:
        agent_file_path = agents_path / agent_name / f"{agent_name}.py"

        # Check if the agent file exists before trying to extract the description
        if agent_file_path.exists():
            descriptions[agent_name] = extract_description_from_file(agent_file_path)
        else:
            print(f"Could not find the file for agent '{agent_name}'.")

    agent_descriptions = "Available agents:\n\n"
    for name, desc in descriptions.items():
        agent_descriptions += f"'{name}': {desc}\n"

    return agent_descriptions