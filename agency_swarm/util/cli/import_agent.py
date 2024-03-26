import os
import shutil
from importlib import resources  # For Python 3.9+ use importlib.resources


def import_agent(agent_name, destination):
    """
    Copies the specified agent files from the package to a specified destination directory,
    preserving the folder structure.
    """
    package = 'agency_swarm.agents'

    # Construct the destination path for the agent
    agent_destination = os.path.join(destination, agent_name)
    if not os.path.exists(agent_destination):
        os.makedirs(agent_destination, exist_ok=True)

    try:
        # Using importlib.resources.files to get a reference to the directory
        agent_folder = resources.files(package) / agent_name

        # Copy each item in the directory to the destination
        for item in agent_folder.iterdir():
            source_path = item
            destination_path = os.path.join(agent_destination, item.name)

            if item.is_dir():
                shutil.copytree(source_path, destination_path, dirs_exist_ok=True)
            else:
                shutil.copy2(source_path, destination_path)

        print(f"Agent '{agent_name}' copied to: {agent_destination}")
    except Exception as e:
        print(f"Error importing agent '{agent_name}'. Most likely the agent name is wrong. Error: {e}")
