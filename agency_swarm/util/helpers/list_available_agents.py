import os
from importlib import resources
def list_available_agents(package='agency_swarm.agents'):
    """
    Lists available agents within the specified package directory.

    :param package: The package containing the agents directory.
    :return: A list of available agent names (subdirectories).
    """
    available_agents = []

    # Use resources.files to access the package directory
    try:
        # For Python 3.9 and newer
        package_dir = resources.files(package)
    except AttributeError:
        # Fallback for Python 3.7 and 3.8 where resources.files is not available
        # This requires the importlib_resources backport
        from importlib_resources import files as package_files
        package_dir = package_files(package)

    # List the contents of the agents directory
    if package_dir.is_dir():
        for entry in package_dir.iterdir():
            if entry.is_dir() and not entry.name.startswith(('.', '_')):
                available_agents.append(entry.name)

    return available_agents