import pkgutil
import importlib
import inspect


def get_class_names_from_submodules(module_name):
    """
    Get all class names from submodules of a given module, excluding the top-level module.

    Args:
    - module_name: The name of the module to search through.

    Returns:
    - A list of class names found within the submodules of the given module.
    """
    class_names = {}
    top_level_module = importlib.import_module(module_name)
    top_level_classes = {cls_name for cls_name, _ in inspect.getmembers(top_level_module, inspect.isclass)}

    try:
        # Walk through all the submodules and subpackages within the package
        for finder, name, is_pkg in pkgutil.walk_packages(top_level_module.__path__,
                                                          prefix=top_level_module.__name__ + '.'):
            # Import the submodule
            submodule = importlib.import_module(name)
            # exclude genesis agents
            if 'genesis' in submodule.__name__ or "oai" in submodule.__name__:
                continue

            # Inspect and collect all classes that are not in the set of top-level classes
            classes_in_submodule = [cls_name for cls_name, cls_obj in inspect.getmembers(submodule, inspect.isclass)
                                    if cls_obj.__module__ == submodule.__name__ and cls_name not in top_level_classes]

            if len(classes_in_submodule) > 0:
                class_names[submodule.__name__] = classes_in_submodule

    except ImportError as e:
        print(f"Error importing module {module_name}: {e}")

    return class_names
