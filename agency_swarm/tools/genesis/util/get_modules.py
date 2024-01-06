import importlib.resources
import pathlib


def get_modules(module_name):
    """
    Get all submodule names from a given module based on file names, without importing them,
    excluding those containing '.agent' or '.genesis' in their paths.

    Args:
    - module_name: The name of the module to search through.

    Returns:
    - A list of submodule names found within the given module.
    """
    submodule_names = []

    try:
        # Using importlib.resources to access the package contents
        with importlib.resources.path(module_name, '') as package_path:
            # Walk through the package directory using pathlib
            for path in pathlib.Path(package_path).rglob('*.py'):
                if path.name != '__init__.py':
                    # Construct the module name from the file path
                    relative_path = path.relative_to(package_path)
                    module_path = '.'.join(relative_path.with_suffix('').parts)

                    submodule_names.append(f"{module_name}.{module_path}")

    except ImportError:
        print(f"Module {module_name} not found.")
        return submodule_names

    submodule_names = [name for name in submodule_names if not name.endswith(".agent") and
                       '.genesis' not in name and
                       'util' not in name and
                       'oai' not in name and
                       'ToolFactory' not in name and
                       'BaseTool' not in name]

    # remove repetition at the end of the path like 'agency_swarm.agents.coding.CodingAgent.CodingAgent'
    for i in range(len(submodule_names)):
        splitted = submodule_names[i].split(".")
        if splitted[-1] == splitted[-2]:
            submodule_names[i] = ".".join(splitted[:-1])

    return submodule_names
